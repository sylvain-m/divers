#!/usr/bin/env python3
"""
Generate an "hyperlapse" video from 360° panoramas (Panoramax) with a camera
whose orientation is interpolated from a start heading/pitch to an end
heading/pitch across the sequence (inspired by TeehanLax "Hyperlapse.js" and cquest "pano2planet.py").

Each equirectangular panorama is re-projected into a perspective viewport,
as if a camera was looking in a given direction.

Dependencies:
    pip install numpy opencv-python pillow requests tqdm
    (ffmpeg optionnel mais recommandé pour la sortie .mp4)

Sur Windows, lancer avec :
    python pano2lapse.py
"""

import os
import sys
import shutil
import subprocess

import cv2
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urljoin
from tqdm import tqdm

# ======================================================================
# CONFIGURATION — modifiez les valeurs ici, puis lancez le script
# ======================================================================

# Entrée : URL de collection/séquence Panoramax (STAC), ou chemins locaux
# vers des panoramas équirectangulaires (jpg, png...).
INPUTS = [
    "https://api.panoramax.xyz/api/collections/bdafb979-f72e-4033-8dd7-c58b63c353d0",
]

# Sortie : fichier vidéo .mp4
OUTPUT = "NomFichier.mp4"

# Dimensions de la vue perspective (la vidéo)
WIDTH = 1920           # largeur en pixels (ex: 1920, 1280)
HEIGHT = 1080          # hauteur en pixels (ex: 1080, 720)

# Champ de vision horizontal de la caméra en degrés
# (ex: 90 = large, 66 = naturel, 45 = téléobjectif)
FOV = 132.0 # 132 était le max sans qu'on voit le logo au nadir

# Orientation de départ et d'arrivée, en degrés boussole :
#   0 = Nord, 90 = Est, 180 = Sud, 270 = Ouest
# L'orientation est interpolée linéairement sur l'ensemble des images
# utilisées. Pour tourner dans le sens des aiguilles d'une montre
# (Nord -> Est -> Sud...), YAW_END > YAW_START.
# Astuce : au-delà de 360 (ex: 0 -> 450) pour plus d'un tour complet ;
# valeurs négatives possibles pour tourner dans l'autre sens (0 -> -90).
YAW_START = 0.0        # cap de départ (ex: 0 = Nord)
YAW_END = 180.0        # cap d'arrivée (ex: 180 = Sud)

# Inclinaison verticale de départ et d'arrivée en degrés
# (0 = horizon, 30 = vers le ciel, -30 = vers le sol)
PITCH_START = 0.0      # ex: 0.0 (horizon), 10.0
PITCH_END = 0.0        # ex: -10.0 (descendre vers le sol)

# Décalage de calibration si l'image du panorama n'est pas alignée Nord = gauche
# (ajoute N degrés à toutes les orientations, ex: 0, 90 ou 180)
YAW_OFFSET = 0.0

FPS = 15.0            # images par seconde de la vidéo
DURATION = 0          # durée max de la vidéo en secondes (0 = illimitée)
START = 150           # démarrer à la Nième photo (0 = début de la séquence)
END = 250             # s'arrêter AVANT la Nième photo (0 = jusqu'à la fin)
                      # ex: START=500, END=800 -> images 500 à 799 uniquement
SUPERSAMPLE = 2       # facteur de rendu interne anti-aliasing (1 à 3)

# ======================================================================
# Fin de la configuration
# ======================================================================


retry_strategy = Retry(
    total=5,
    connect=3,
    status_forcelist=[429, 500, 502, 503, 504],
    backoff_factor=1.5,
    backoff_jitter=0.2,
    respect_retry_after_header=True,
)
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=retry_strategy))


def imread_url(url: str):
    """Download an image as BGRA."""
    r = session.get(url, timeout=30)
    r.raise_for_status()
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("bad image")
    return img


def count_panoramax_items(collection_url: str):
    """Get number of items in a STAC collection"""
    r = session.get(collection_url, timeout=60)
    r.raise_for_status()
    collection = r.json()
    return collection["stats:items"]["count"]


def iter_panoramax_items(collection_url: str, limit: int = 500):
    """Generator of STAC Items from a Panoramax collection."""
    next_url = collection_url.rstrip("/") + "/items"
    params = {"limit": limit}

    while next_url:
        r = session.get(next_url, params=params, timeout=60)
        r.raise_for_status()
        page = r.json()

        yield from page.get("features", [])

        next_link = next(
            (l["href"] for l in page.get("links", []) if l.get("rel") == "next"),
            None,
        )
        next_url = urljoin(next_url, next_link) if next_link else None
        params = {}


def get_sd_picture_asset_url(item: dict):
    """Return the SD/standard 2048px picture asset URL from a STAC Item."""
    assets = item.get("assets") or {}

    def width(a):
        return a.get("width") or a.get("proj:width") or a.get("px:width")

    def href(a):
        return a.get("href") or a.get("url")

    for name, a in assets.items():
        h = href(a)
        if h and (
            width(a) == 2048
            or "sd" in name.lower()
            or "standard" in name.lower()
            or "2048" in h.lower()
        ):
            return h

    return None


def load_image(path: str):
    """Load a local image as BGR."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f"error: could not read image '{path}'")
    return img


def precompute_viewport(width, height, fov_deg, supersample):
    """
    Precompute the *relative* angles of every viewport pixel, independent of
    the camera orientation (so only a cheap shift is needed per frame).

    Returns (rel_heading, rel_pitch) in radians, at render resolution
    (width * supersample, height * supersample).
    """
    w = width * max(1, supersample)
    h = height * max(1, supersample)

    f = (w / 2.0) / np.tan(np.deg2rad(fov_deg) / 2.0)   # focal length in px
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0

    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32),
                         np.arange(h, dtype=np.float32))
    dx = xs - cx
    dy = cy - ys                                        # y axis points up

    # Gnomonic (true pinhole) projection:
    rel_heading = np.arctan2(dx, f)                    # horizontal angle
    rel_pitch = np.arctan2(dy, np.sqrt(dx * dx + f * f))  # vertical angle
    return rel_heading, rel_pitch


def render_view(src, rel_heading, rel_pitch, yaw_deg, pitch_deg, supersample):
    """
    Re-project `src` (equirectangular BGR) into the perspective viewport
    of a camera looking at yaw/pitch (degrees, 0=N / horizon).
    """
    h, w = src.shape[:2]

    # Global direction of every pixel
    lon = np.deg2rad(yaw_deg) + rel_heading            # heading (rad)
    lat = np.deg2rad(pitch_deg) + rel_pitch           # pitch (rad)

    # Equirectangular coordinates: u = longitude fraction, v = latitude fraction
    u = (lon / (2.0 * np.pi)) % 1.0
    v = (0.5 * np.pi - lat) / np.pi
    v = np.clip(v, 0.0, 1.0)                          # clamp near poles

    map_x = (u * w).astype(np.float32)
    map_y = (v * h).astype(np.float32)

    out = cv2.remap(src, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_WRAP)

    if supersample > 1:
        out = cv2.resize(out, (out.shape[1] // supersample,
                               out.shape[0] // supersample),
                         interpolation=cv2.INTER_AREA)
    return out


def open_ffmpeg(out_path: str, width, height, fps: float):
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-framerate", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        out_path,
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)


def write_frame(writer, frame):
    if isinstance(writer, subprocess.Popen):
        try:
            writer.stdin.write(np.ascontiguousarray(frame).data)
        except BrokenPipeError:
            sys.exit("error: ffmpeg stopped writing")
    else:
        writer.write(frame)


def main():
    width, height = WIDTH, HEIGHT
    fps = FPS
    supersample = SUPERSAMPLE

    if supersample < 1 or supersample > 3:
        sys.exit("error: SUPERSAMPLE must be between 1 and 3")
    if fps <= 0:
        sys.exit("error: FPS must be greater than 0")
    if not OUTPUT.lower().endswith(".mp4"):
        sys.exit("error: OUTPUT must be a .mp4 file")

    video_dir = os.path.dirname(OUTPUT) or "."
    os.makedirs(video_dir, exist_ok=True)

    if shutil.which("ffmpeg"):
        writer = open_ffmpeg(OUTPUT, width, height, fps)
    else:
        print("⚠️ ffmpeg not found, using OpenCV writer instead")
        writer = None
        for codec in ("avc1", "mp4v"):
            writer = cv2.VideoWriter(
                OUTPUT, cv2.VideoWriter_fourcc(*codec), fps, (width, height))
            if writer.isOpened():
                break

    # Static viewport geometry (computed once)
    rel_heading, rel_pitch = precompute_viewport(width, height, FOV, supersample)

    # Gather the list of source images (URLs or local paths)
    sources = []
    for path in INPUTS:
        if path[:4] == "http":
            print(f"Collecting items from {path} ...")
            total = count_panoramax_items(path)
            print(f"{total} pictures in collection")
            for item in tqdm(iter_panoramax_items(path),
                             total=int(total), desc="Listing"):
                url = get_sd_picture_asset_url(item)
                if url:
                    sources.append(url)
        else:
            sources.append(path)

    if START > 0:
        sources = sources[START:]
    if END > START:
        sources = sources[:END - START]

    # Number of frames actually used
    max_frames = int(DURATION * fps) if DURATION else 0
    if max_frames and len(sources) > max_frames:
        print(f"⚠️ using only the first {max_frames} pictures "
              f"(DURATION = {DURATION}s at {fps} fps)")
        sources = sources[:max_frames]

    n = len(sources)
    if n == 0:
        sys.exit("error: no source image found")
    print(f"{n} frames, yaw {YAW_START}° -> {YAW_END}°, "
          f"pitch {PITCH_START}° -> {PITCH_END}°")

    for i, src_ref in enumerate(tqdm(sources, desc="Frames")):
        # Interpolate camera orientation linearly across the sequence
        if n == 1:
            t = 0.0
        else:
            t = i / (n - 1)
        yaw = YAW_START + (YAW_END - YAW_START) * t + YAW_OFFSET
        pitch = PITCH_START + (PITCH_END - PITCH_START) * t

        if src_ref[:4] == "http":
            src = imread_url(src_ref)
        else:
            src = load_image(src_ref)

        frame = render_view(src, rel_heading, rel_pitch, yaw, pitch, supersample)
        write_frame(writer, frame)

    if isinstance(writer, subprocess.Popen):
        try:
            writer.stdin.close()
        except BrokenPipeError:
            pass
        if writer.wait() != 0:
            sys.exit("error: ffmpeg failed")
    else:
        writer.release()
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()

import os
import requests
import json
from datetime import datetime

# Modes de transport à exporter :
transports = ['uav', 'UAV', 'drone', 'DRONE']

# Configuration pour l'instance Panoramax OpenStreetMap France
PANORAMAX_API_URL = "https://panoramax.openstreetmap.fr/api"
SEARCH_ENDPOINT = f"{PANORAMAX_API_URL}/search"

# Crée le chemin absolu vers le dossier de sortie
output_dir = os.path.join(os.getcwd(), "osm", "panoramax")
os.makedirs(output_dir, exist_ok=True)  # Crée le dossier s'il n'existe pas

# Chemin complet du fichier de sortie
OUTPUT_FILE = os.path.join(output_dir, "panoramax_osm_transport_uav_sequences.geojson")

def fetch_transport_sequences(transport):
    search_sequences_params = {
        "filter": f'"semantics.transport"=\'{transport}\'',
        "limit": 10000
    }
    try:
        response = requests.get(SEARCH_ENDPOINT, params=search_sequences_params)
        response.raise_for_status()
        data = response.json()
        return data.get("features", [])
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la requête pour les séquences avec le tag '{transport}' : {e}")
        return []

def export_sequences(sequences):
    # Vérifier si les séquences ont une géométrie
    has_geometry = any("geometry" in sequence for sequence in sequences)
    if has_geometry:
        # Exporter en GeoJSON
        geojson_output = {
            "type": "FeatureCollection",
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "source": "panoramax.openstreetmap.fr",
                "transport_type": "uav/UAV"
            },
            "features": []
        }
        for sequence in sequences:
            sequence_id = sequence.get("id")
            geometry = sequence.get("geometry", {})
            properties = sequence.get("properties", {})
            semantics = properties.get("collection", {}).get("semantics", [])
            geojson_feature = {
                "type": "Feature",
                "id": sequence_id,
                "geometry": geometry,
                "properties": {
                    "semantics": semantics,
                    "properties": properties
                }
            }
            geojson_output["features"].append(geojson_feature)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
            json.dump(geojson_output, file, ensure_ascii=False, indent=2)
    else:
        # Exporter en JSON simple
        json_output = {
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "source": "panoramax.openstreetmap.fr",
                "transport_type": "uav/UAV"
            },
            "sequences": []
        }
        for sequence in sequences:
            sequence_id = sequence.get("id")
            properties = sequence.get("properties", {})
            semantics = properties.get("collection", {}).get("semantics", [])
            json_output["sequences"].append({
                "id": sequence_id,
                "semantics": semantics,
                "properties": properties
            })
        with open(OUTPUT_FILE.replace('.geojson', '.json'), "w", encoding="utf-8") as file:
            json.dump(json_output, file, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    all_sequences = []
    for transport in transports:
        print(f"Récupération des séquences avec le tag 'transport={transport}' depuis panoramax.openstreetmap.fr...")
        sequences = fetch_transport_sequences(transport)
        if sequences:
            print(f"Trouvé {len(sequences)} séquences avec le tag 'transport={transport}'.")
            all_sequences.extend(sequences)
        else:
            print(f"Aucune séquence trouvée avec le tag 'transport={transport}'.")

    if all_sequences:
        print(f"Total de {len(all_sequences)} séquences trouvées.")
        export_sequences(all_sequences)
        print(f"Export terminé. Résultat enregistré dans {OUTPUT_FILE}.")
    else:
        print("Aucune séquence trouvée.")

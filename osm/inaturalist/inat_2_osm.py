import requests
import pandas as pd
import time

# --- Configuration ---
INATURALIST_API_URL = "https://api.inaturalist.org/v1"
OBSERVATIONS_ENDPOINT = "/observations"
FIELD_NAME_OSM = "OpenStreetMap (OSM)"
PAGE_SIZE = 200
CSV_INPUT = "inat_osm.csv"
CSV_OUTPUT = "osm_inat.csv"

# --- Fonction pour récupérer les observations avec le champ OSM ---
def fetch_observations_with_osm_field():
    observations = []
    page = 1
    total_results = None

    while True:
        params = {
            "page": page,
            "per_page": PAGE_SIZE,
            "field:{}".format(FIELD_NAME_OSM): "",
        }

        print(f"Récupération de la page {page}...")
        response = requests.get(
            f"{INATURALIST_API_URL}{OBSERVATIONS_ENDPOINT}",
            params=params
        )
        print(f"Statut de la réponse : {response.status_code}")  # Debug
        response.raise_for_status()
        data = response.json()

        if total_results is None:
            total_results = data["total_results"]
            print(f"Nombre total d'observations à récupérer : {total_results}")

        observations.extend(data["results"])
        print(f"Observations récupérées jusqu'à présent : {len(observations)}")

        if len(observations) >= total_results:
            break

        page += 1
        time.sleep(1)  # Respecter les limites de l'API

    return observations

# --- Fonction pour extraire les données OSM des observations ---
def extract_osm_data(observations):
    osm_data = []
    for obs in observations:
        for field in obs.get("ofvs", []):
            if field.get("name") == FIELD_NAME_OSM:
                osm_url = field.get("value")
                if osm_url and osm_url.startswith("https://www.openstreetmap.org/"):
                    osm_data.append({
                        "obs_id": obs["id"],
                        "osm_url": osm_url
                    })
    print(f"Nombre total d'observations avec champ OSM : {len(osm_data)}")  # Debug
    return osm_data

# --- Fonction pour transformer les données OSM ---
def transform_osm_data(osm_data):
    if not osm_data:
        print("Aucune donnée OSM à transformer.")
        return pd.DataFrame(columns=["osm_element", "osm_id", "osm_url", "obs_ids", "obs_url"])

    df = pd.DataFrame(osm_data)

    # Supprimer les doublons et forcer une copie
    df_unique = df.drop_duplicates(subset=["osm_url"]).copy()
    print(f"Nombre d'URLs OSM uniques : {len(df_unique)}")  # Debug

    # Extraire osm_element et osm_id
    def parse_osm_url(url):
        parts = url.split("/")
        osm_element = parts[-2]
        osm_id = parts[-1]
        return osm_element, osm_id

    df_unique[["osm_element", "osm_id"]] = df_unique["osm_url"].apply(
        lambda x: pd.Series(parse_osm_url(x))
    )

    # Regrouper par osm_url et agréger les obs_id (triés par ordre ascendant)
    df_grouped = df.groupby("osm_url").agg({
        "obs_id": lambda x: ";".join(map(str, sorted(x, key=int)))
    }).reset_index()

    # Fusionner avec les données uniques
    df_final = pd.merge(
        df_unique[["osm_url", "osm_element", "osm_id"]],
        df_grouped,
        on="osm_url",
        how="left"
    )

    # Renommer la colonne obs_id en obs_ids
    df_final = df_final.rename(columns={"obs_id": "obs_ids"})

    # Ajouter la colonne obs_url
    df_final["obs_url"] = df_final["obs_ids"].apply(
        lambda x: f"https://www.inaturalist.org/observations?verifiable=any&id={x.replace(';', ',')}"
    )

    # Réorganiser les colonnes dans l'ordre souhaité
    df_final = df_final[["osm_element", "osm_id", "osm_url", "obs_ids", "obs_url"]]
    print(f"Nombre de lignes dans le DataFrame final : {len(df_final)}")  # Debug

    return df_final

# --- Exécution ---
if __name__ == "__main__":
    print("=== Début de l'exécution du script ===")
    print("Récupération des observations avec le champ OSM...")
    observations = fetch_observations_with_osm_field()

    print("\nExtraction des données OSM...")
    osm_data = extract_osm_data(observations)

    if not osm_data:
        print("Aucune observation avec le champ OSM trouvée.")
        # Créer des fichiers CSV vides avec les en-têtes
        pd.DataFrame(columns=["obs_id", "osm_url"]).to_csv(CSV_INPUT, index=False)
        pd.DataFrame(columns=["osm_element", "osm_id", "osm_url", "obs_ids", "obs_url"]).to_csv(CSV_OUTPUT, index=False)
    else:
        # Sauvegarder le CSV intermédiaire
        df_osm = pd.DataFrame(osm_data)
        df_osm.to_csv(CSV_INPUT, index=False)
        print(f"Fichier intermédiaire '{CSV_INPUT}' généré avec {len(df_osm)} lignes.")

        # Transformer les données
        df_final = transform_osm_data(osm_data)
        df_final.to_csv(CSV_OUTPUT, index=False)
        print(f"Fichier final '{CSV_OUTPUT}' généré avec {len(df_final)} lignes.")

    print("=== Fin de l'exécution du script ===")

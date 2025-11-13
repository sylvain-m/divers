import requests
import json
# from datetime import datetime

# Mode de transport à exporter :
transport = 'uav'

# Horodatage de l'export (désactivé ici)
# now = datetime.now()
# nowtxt = now.strftime('%Y%m%d-%Hh%M')

# Configuration pour l'instance Panoramax OpenStreetMap France
PANORAMAX_API_URL = "https://panoramax.openstreetmap.fr/api"
SEARCH_ENDPOINT = f"{PANORAMAX_API_URL}/search"
# OUTPUT_FILE = "panoramax_osm_transport_" + transport + "_sequences_" + nowtxt + ".geojson"  # version horodatée
OUTPUT_FILE = "panoramax_osm_transport_" + transport + "_sequences.geojson"  # version non horodatée

# Paramètres de recherche pour les séquences avec le tag "transport"
search_sequences_params = {
    "filter": '"semantics.transport"=\'' + transport + '\'',
    "limit": 10000
}

def fetch_transport_sequences():
    try:
        response = requests.get(SEARCH_ENDPOINT, params=search_sequences_params)
        response.raise_for_status()
        data = response.json()
        return data.get("features", [])
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la requête pour les séquences : {e}")
        return []

def export_sequences(sequences):
    # Vérifier si les séquences ont une géométrie
    has_geometry = any("geometry" in sequence for sequence in sequences)

    if has_geometry:
        # Exporter en GeoJSON
        geojson_output = {
            "type": "FeatureCollection",
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
        json_output = []
        for sequence in sequences:
            sequence_id = sequence.get("id")
            properties = sequence.get("properties", {})
            semantics = properties.get("collection", {}).get("semantics", [])

            json_output.append({
                "id": sequence_id,
                "semantics": semantics,
                "properties": properties
            })

        with open(OUTPUT_FILE.replace('.geojson', '.json'), "w", encoding="utf-8") as file:
            json.dump(json_output, file, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    print("Récupération des séquences avec le tag 'transport=" + transport + "' depuis panoramax.openstreetmap.fr...")
    sequences = fetch_transport_sequences()
    if sequences:
        print(f"Trouvé {len(sequences)} séquences avec le tag 'transport=" + transport + "'.")
        export_sequences(sequences)
        print(f"Export terminé. Résultat enregistré dans {OUTPUT_FILE}.")
    else:
        print("Aucune séquence trouvée avec le tag 'transport=" + transport + "'.")

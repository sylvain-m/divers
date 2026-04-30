import requests
import pandas as pd
import json

OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"

def build_overpass_query(df):
    nodes = []
    ways = []
    relations = []

    for _, row in df.iterrows():
        element_type = row["osm_element"]
        element_id = int(row["osm_id"])
        if element_type == "node":
            nodes.append(f"node({element_id});")
        elif element_type == "way":
            ways.append(f"way({element_id});")
        elif element_type == "relation":
            relations.append(f"relation({element_id});")

    query_parts = []
    if nodes:
        query_parts.append("\n".join(nodes))
    if ways:
        query_parts.append("\n".join(ways))
    if relations:
        query_parts.append("\n".join(relations))

    if not query_parts:
        return None

    return """[out:json];
(
{query_elements}
);
out geom meta;
""".format(query_elements=";\n".join(query_parts))



def fetch_all_osm_elements(df):
    query = build_overpass_query(df)
    if not query:
        print("Warning: No elements to query in the CSV.")
        return []

    print("Sending Overpass query (POST)...")
    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60
        )
        response.raise_for_status()
        return response.json().get("elements", [])
    except requests.exceptions.RequestException as e:
        print(f"Error during Overpass query: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Server response: {e.response.text}")
        return []

def main():
    try:
        df = pd.read_csv("osm_inat.csv")
        print(f"CSV loaded: {len(df)} rows.")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    elements = fetch_all_osm_elements(df)
    if not elements:
        print("Warning: No data returned from Overpass.")
        return

    osm_to_obs = {}
    for _, row in df.iterrows():
        key = (row["osm_element"], int(row["osm_id"]))
        osm_to_obs[key] = {
            "obs_ids": row.get("obs_ids", ""),
            "obs_url": row.get("obs_url", "")
        }

    features = []
    for element in elements:
        element_type = element["type"]
        element_id = element["id"]
        obs_data = osm_to_obs.get((element_type, element_id), {})
        obs_ids = obs_data.get("obs_ids", "")
        obs_url = obs_data.get("obs_url", "")

        if element_type == "node":
            geometry = {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
        elif element_type == "way":
            node_ids = element["nodes"]
            node_coords = []
            for node in elements:
                if node["type"] == "node" and node["id"] in node_ids:
                    node_coords.append([node["lon"], node["lat"]])
            geometry = {"type": "LineString", "coordinates": node_coords}
        elif element_type == "relation":
            geometries = []
            for member in element.get("members", []):
                member_type = member["type"]
                member_id = member["ref"]
                for member_element in elements:
                    if member_element["type"] == member_type and member_element["id"] == member_id:
                        if member_type == "node":
                            geometries.append({"type": "Point", "coordinates": [member_element["lon"], member_element["lat"]]})
                        elif member_type == "way":
                            way_node_ids = member_element["nodes"]
                            way_coords = []
                            for node in elements:
                                if node["type"] == "node" and node["id"] in way_node_ids:
                                    way_coords.append([node["lon"], node["lat"]])
                            geometries.append({"type": "LineString", "coordinates": way_coords})
            geometry = {"type": "GeometryCollection", "geometries": geometries} if geometries else None
        else:
            continue

        features.append({
            "type": "Feature",
            "properties": {
                "id": element_id,
                "type": element_type,
                "tags": element.get("tags", {}),
                "obs_ids": obs_ids,
                "obs_url": obs_url
            },
            "geometry": geometry
        })

    output = {"type": "FeatureCollection", "features": features}
    with open("osm_inat.geojson", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("GeoJSON file generated: osm_inat.geojson")

if __name__ == "__main__":
    main()

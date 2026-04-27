import duckdb
import json
from datetime import datetime

# Connexion à DuckDB
conn = duckdb.connect()

# Exécution de la requête et export en GeoJSON
conn.execute("""
    INSTALL spatial;
    LOAD spatial;
    COPY (
        SELECT *,
            providers[1].name as provider_name
        FROM 'https://api.panoramax.xyz/data/geoparquet/panoramax.parquet'
        WHERE length(list_filter(semantics, s ->
            s.key = 'transport' AND
            (LOWER(s.value) = 'uav' OR LOWER(s.value) = 'drone')
        )) > 0
    ) TO 'osm/panoramax/sequences_uav_drone.geojson' WITH (FORMAT GDAL, DRIVER 'GeoJSON');
""")

# Lire, modifier et réécrire le GeoJSON
with open('osm/panoramax/sequences_uav_drone.geojson', 'r+', encoding='utf-8') as f:
    data = json.load(f)

    # Créer une nouvelle structure avec metadata après name
    new_data = {
        "type": data["type"],
        "name": data.get("name", ""),  # Conserve le champ name s'il existe
        "metadata": {"export_date": datetime.now().isoformat()},
        "features": data["features"],
        # Copie les autres champs éventuels (crs, bbox, etc.)
        **{k: v for k, v in data.items() if k not in ["type", "name", "features"]}
    }

    f.seek(0)
    json.dump(new_data, f, indent=2, ensure_ascii=False)
    f.truncate()

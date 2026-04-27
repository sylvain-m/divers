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

# Ajouter la métadonnée de date
with open('osm/panoramax/sequences_uav_drone.geojson', 'r+', encoding='utf-8') as f:
    data = json.load(f)
    data['metadata'] = {'export_date': datetime.now().isoformat()}
    f.seek(0)
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.truncate()

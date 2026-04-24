import duckdb

# Connexion à DuckDB
conn = duckdb.connect()

# Exécution de la requête et export en GeoJSON
conn.execute("""
    INSTALL spatial;
    LOAD spatial;
    COPY (
        SELECT *
        FROM 'https://api.panoramax.xyz/data/geoparquet/panoramax.parquet'
        WHERE length(list_filter(semantics, s ->
            s.key = 'transport' AND
            (LOWER(s.value) = 'uav' OR LOWER(s.value) = 'drone')
        )) > 0
    ) TO 'osm/panoramax/sequences_uav_drone.geojson' WITH (FORMAT GDAL, DRIVER 'GeoJSON');
""")

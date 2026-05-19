import json
import time
import requests
import pandas as pd

CSV_INPUT = "osm_inat.csv"
GEOJSON_OUTPUT = "osm_inat.geojson"

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
]

INITIAL_BATCH_SIZE = 10
TIMEOUT = 120
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": "Python OSM Downloader"
}


def build_query(batch_df):

    query_lines = []

    for _, row in batch_df.iterrows():

        try:
            osm_type = str(
                row["osm_element"]
            ).strip().lower()

            osm_id = int(
                row["osm_id"]
            )

        except Exception:
            continue

        if osm_type in [
            "node",
            "way",
            "relation"
        ]:

            query_lines.append(
                f"{osm_type}({osm_id});"
            )

    if not query_lines:
        return None

    return f"""
[out:json][timeout:90];
(
{''.join(query_lines)}
);
out geom tags;
"""


def fetch_query(query):

    for server in OVERPASS_SERVERS:

        for attempt in range(MAX_RETRIES):

            try:

                response = requests.post(
                    server,
                    data={"data": query},
                    timeout=TIMEOUT,
                    headers=HEADERS
                )

                response.raise_for_status()

                return response.json().get(
                    "elements",
                    []
                )

            except Exception as e:

                print(
                    f"Retry "
                    f"{attempt + 1}/"
                    f"{MAX_RETRIES} "
                    f"failed on "
                    f"{server}"
                )

                print(e)

                time.sleep(
                    3 * (
                        attempt + 1
                    )
                )

    return None


def fetch_batch_recursive(batch_df):

    if len(batch_df) == 0:
        return []

    query = build_query(
        batch_df
    )

    if query is None:
        return []

    elements = fetch_query(
        query
    )

    if elements is not None:

        print(
            f"{len(elements)} "
            f"elements downloaded"
        )

        return elements

    if len(batch_df) == 1:

        row = batch_df.iloc[0]

        print(
            "Failed element:",
            row["osm_element"],
            row["osm_id"]
        )

        return []

    print(
        f"Splitting batch "
        f"({len(batch_df)} "
        f"elements)"
    )

    middle = (
        len(batch_df) // 2
    )

    left = batch_df.iloc[
        :middle
    ]

    right = batch_df.iloc[
        middle:
    ]

    return (
        fetch_batch_recursive(
            left
        )
        +
        fetch_batch_recursive(
            right
        )
    )


def osm_to_geometry(element):

    osm_type = element[
        "type"
    ]

    if osm_type == "node":

        return {
            "type": "Point",
            "coordinates": [
                element["lon"],
                element["lat"]
            ]
        }

    geometry = element.get(
        "geometry"
    )

    if not geometry:
        return None

    coordinates = [
        [
            point["lon"],
            point["lat"]
        ]
        for point in geometry
    ]

    if osm_type == "way":

        if (
            len(coordinates)
            >= 4
            and coordinates[0]
            ==
            coordinates[-1]
        ):

            return {
                "type":
                "Polygon",
                "coordinates":
                [coordinates]
            }

        return {
            "type":
            "LineString",
            "coordinates":
            coordinates
        }

    if osm_type == "relation":

        return {
            "type":
            "LineString",
            "coordinates":
            coordinates
        }

    return None


def main():

    print(
        "Reading CSV..."
    )

    df = pd.read_csv(
        CSV_INPUT
    )

    print(
        f"{len(df)} "
        f"rows loaded"
    )

    all_elements = []

    total_batches = (
        len(df)
        +
        INITIAL_BATCH_SIZE
        -
        1
    ) // INITIAL_BATCH_SIZE

    for i in range(
        0,
        len(df),
        INITIAL_BATCH_SIZE
    ):

        batch_number = (
            i //
            INITIAL_BATCH_SIZE
            + 1
        )

        print(
            f"Batch "
            f"{batch_number}/"
            f"{total_batches}"
        )

        batch_df = df.iloc[
            i:
            i
            +
            INITIAL_BATCH_SIZE
        ]

        elements = (
            fetch_batch_recursive(
                batch_df
            )
        )

        all_elements.extend(
            elements
        )

        time.sleep(2)

    print(
        "Building GeoJSON..."
    )

    csv_lookup = {}

    for _, row in (
        df.iterrows()
    ):

        try:

            key = (
                str(
                    row[
                        "osm_element"
                    ]
                )
                .lower(),
                int(
                    row[
                        "osm_id"
                    ]
                )
            )

            csv_lookup[
                key
            ] = (
                row.to_dict()
            )

        except Exception:
            pass

    features = []

    for element in (
        all_elements
    ):

        key = (
            element["type"],
            element["id"]
        )

        row_data = (
            csv_lookup.get(
                key,
                {}
            )
        )

        geometry = (
            osm_to_geometry(
                element
            )
        )

        if geometry is None:
            continue

        properties = (
            row_data.copy()
        )

        properties[
            "tags"
        ] = (
            element.get(
                "tags",
                {}
            )
        )

        features.append({
            "type":
            "Feature",
            "geometry":
            geometry,
            "properties":
            properties
        })

    geojson = {
        "type":
        "FeatureCollection",
        "features":
        features
    }

    with open(
        GEOJSON_OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            geojson,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Done: "
        f"{len(features)} "
        f"features saved "
        f"to "
        f"{GEOJSON_OUTPUT}"
    )


if __name__ == "__main__":
    main()

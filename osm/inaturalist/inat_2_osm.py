import requests
import pandas as pd
import time
from datetime import datetime

# --- Configuration ---
INATURALIST_API_URL = "https://api.inaturalist.org/v1"
OBSERVATIONS_ENDPOINT = "/observations"
FIELD_NAME_OSM = "OpenStreetMap (OSM)"
PAGE_SIZE = 200
CSV_INPUT = "inat_osm.csv"
CSV_OUTPUT = "osm_inat.csv"
LOG_FILE = "inat_2_csv_log.txt"

# --- Function to write to the log file ---
def write_to_log(inat_lines, osm_lines):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} : {inat_lines} iNat observations for {osm_lines} OSM objects\n")

# --- Function to fetch observations with the OSM field ---
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

        print(f"Fetching page {page}...")
        try:
            response = requests.get(
                f"{INATURALIST_API_URL}{OBSERVATIONS_ENDPOINT}",
                params=params
            )
            print(f"Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()

            if total_results is None:
                total_results = data["total_results"]
                print(f"Total observations to fetch: {total_results}")

            observations.extend(data["results"])
            print(f"Observations fetched so far: {len(observations)}")

            if len(observations) >= total_results:
                break

            page += 1
            time.sleep(1)  # Respect API rate limits

        except Exception as e:
            print(f"Error fetching observations (page {page}): {str(e)}")
            break

    return observations

# --- Function to extract OSM data from observations ---
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
    print(f"Total observations with OSM field: {len(osm_data)}")
    return osm_data

# --- Function to transform OSM data ---
def transform_osm_data(osm_data):
    if not osm_data:
        print("No OSM data to transform.")
        return pd.DataFrame(columns=["osm_element", "osm_id", "osm_url", "obs_ids", "obs_url"])

    df = pd.DataFrame(osm_data)
    df_unique = df.drop_duplicates(subset=["osm_url"]).copy()
    print(f"Number of unique OSM URLs: {len(df_unique)}")

    def parse_osm_url(url):
        url = url.rstrip('/')
        parts = url.split("/")
        osm_element = parts[-2]
        osm_id = parts[-1]
        return osm_element, osm_id

    df_unique[["osm_element", "osm_id"]] = df_unique["osm_url"].apply(
        lambda x: pd.Series(parse_osm_url(x))
    )

    df_grouped = df.groupby("osm_url").agg({
        "obs_id": lambda x: ";".join(map(str, sorted(x, key=int)))
    }).reset_index()

    df_final = pd.merge(
        df_unique[["osm_url", "osm_element", "osm_id"]],
        df_grouped,
        on="osm_url",
        how="left"
    )

    df_final = df_final.rename(columns={"obs_id": "obs_ids"})
    df_final["obs_url"] = df_final["obs_ids"].apply(
        lambda x: f"https://www.inaturalist.org/observations?verifiable=any&id={x.replace(';', ',')}"
    )
    df_final = df_final[["osm_element", "osm_id", "osm_url", "obs_ids", "obs_url"]]
    print(f"Number of rows in final DataFrame: {len(df_final)}")
    return df_final

# --- Execution ---
if __name__ == "__main__":
    print("=== Script execution started ===")

    try:
        print("Fetching observations with OSM field...")
        observations = fetch_observations_with_osm_field()

        print("\nExtracting OSM data...")
        osm_data = extract_osm_data(observations)

        if not osm_data:
            print("No observations with OSM field found.")
            # Create empty CSV files with headers
            pd.DataFrame(columns=["obs_id", "osm_url"]).to_csv(CSV_INPUT, index=False)
            pd.DataFrame(columns=["osm_element", "osm_id", "osm_url", "obs_ids", "obs_url"]).to_csv(CSV_OUTPUT, index=False)
            write_to_log(0, 0)  # Log with 0 observations and 0 OSM objects
        else:
            df_osm = pd.DataFrame(osm_data)
            df_osm.to_csv(CSV_INPUT, index=False)
            print(f"Intermediate file '{CSV_INPUT}' generated with {len(df_osm)} rows.")

            df_final = transform_osm_data(osm_data)
            df_final.to_csv(CSV_OUTPUT, index=False)
            print(f"Final file '{CSV_OUTPUT}' generated with {len(df_final)} rows.")

            # Write to log
            write_to_log(len(df_osm), len(df_final))

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        write_to_log(0, 0)  # Log with 0 in case of error

    print("=== Script execution finished ===")

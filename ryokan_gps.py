import os
import time

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from tqdm import tqdm

# --- Configuration ---
INPUT_FILE = "ryokans_db.csv"
USER_AGENT = "ryokan_explorer_app_v1"


def clean_address(address):
    """
    Cleans up the address to help the geocoder.
    Removes instructions like 'Show map' or excess whitespace.
    """
    if not isinstance(address, str):
        return ""
    # Remove the common scrap artifact "Show map" if present
    cleaned = address.replace("Show map", "").strip()
    return cleaned


def fetch_gps_data():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Please run the scraper first.")
        return

    # Load the database
    # Note: We use sep=';' because that's how we generated it
    df = pd.read_csv(INPUT_FILE, sep=";")

    # Initialize columns if they don't exist
    if "lat" not in df.columns:
        df["lat"] = None
    if "lon" not in df.columns:
        df["lon"] = None

    # Initialize Geocoder
    # timeout=10 ensures we don't hang forever on bad connections
    geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)

    # RateLimiter allows us to automatically respect the 1-second delay rule
    # imposed by OpenStreetMap's free API.
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)

    print("Starting GPS retrieval...")
    print(
        "NOTE: This process includes a 1.1s delay per request to respect API limits."
    )

    # Iterate through the DataFrame
    # We only process rows where 'lat' is missing (NaN)
    missing_coords_mask = df["lat"].isna()
    rows_to_process = df[missing_coords_mask]

    if rows_to_process.empty:
        print("All ryokans already have GPS coordinates. Nothing to do.")
        return

    # Use tqdm to show a progress bar
    with tqdm(total=len(rows_to_process), desc="Geocoding Ryokans") as pbar:
        for index, row in rows_to_process.iterrows():
            address = clean_address(row["location"])
            name = row["name"]

            location = None

            # Strategy 1: Try the exact address
            if address:
                try:
                    location = geocode(address)
                except Exception as e:
                    tqdm.write(f"⚠️ Error geocoding address for {name}: {e}")

            # Strategy 2: If address fails, try "Name + Japan"
            if not location and name:
                try:
                    search_query = f"{name} Japan"
                    location = geocode(search_query)
                except Exception as e:
                    tqdm.write(f"⚠️ Error geocoding name for {name}: {e}")

            # Update the DataFrame if found
            if location:
                df.at[index, "lat"] = location.latitude
                df.at[index, "lon"] = location.longitude
            else:
                # Optional: Mark as unfound so we don't retry endlessly?
                # For now we leave it None or you could set it to 0.
                pass

            # Update progress bar
            pbar.update(1)

            # Save progressively every 10 rows (in case script crashes)
            if index % 10 == 0:
                df.to_csv(
                    INPUT_FILE, sep=";", index=False, encoding="utf-8-sig"
                )

    # Final Save
    df.to_csv(INPUT_FILE, sep=";", index=False, encoding="utf-8-sig")

    # Summary
    success_count = df["lat"].count()
    total_count = len(df)
    print(f"\n✅ Finished! {success_count}/{total_count} ryokans located.")
    print(f"Database updated: {INPUT_FILE}")


if __name__ == "__main__":
    fetch_gps_data()

import os
import webbrowser

import folium
import pandas as pd
from folium.plugins import Fullscreen, MarkerCluster

INPUT_FILE = "ryokans_db.csv"
OUTPUT_MAP = "ryokan_map.html"


def generate_map():
    if not os.path.exists(INPUT_FILE):
        print("Database not found.")
        return

    df = pd.read_csv(INPUT_FILE, sep=";")

    # Filter out rows that still don't have coordinates
    df = df.dropna(subset=["lat", "lon"])

    if df.empty:
        print("No GPS data found. Please run 'ryokan_gps.py' first.")
        return

    # Create Map centered on Japan
    m = folium.Map(
        location=[36.2048, 138.2529], zoom_start=5, tiles="CartoDB positron"
    )
    Fullscreen().add_to(m)
    marker_cluster = MarkerCluster().add_to(m)

    print(f"Plotting {len(df)} ryokans on the map...")

    for _, row in df.iterrows():
        # Color Logic
        color = "blue"
        price = row["price_range_min"]
        if price > 100000:
            color = "black"  # Ultra Luxury
        elif price > 60000:
            color = "purple"  # Luxury
        elif price > 30000:
            color = "orange"  # Expensive
        elif price > 0:
            color = "green"  # Standard

        # Popup Content
        html = f"""
        <div style="font-family: sans-serif; min-width: 200px;">
            <h4 style="margin:0;">{row['name']}</h4>
            <p style="color:gray; font-size:11px; margin-top:2px;">{row['location']}</p>
            <hr style="margin:5px 0;">
            <b>Price:</b> ¥{row['price_range_min']:,}<br>
            <b>Private Bath:</b> {'Yes' if row['room_with_open_air_bath'] else 'No'}<br>
            <b>Rating:</b> {row['tripadvisor_rating']} ⭐<br>
            <br>
            <a href="{row['url']}" target="_blank" style="text-decoration:none; background:#d9534f; color:white; padding:4px 8px; border-radius:3px; font-size:12px;">View Details</a>
        </div>
        """

        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(html, max_width=300),
            tooltip=f"{row['name']} (¥{price:,})",
            icon=folium.Icon(color=color, icon="hot-tub-person", prefix="fa"),
        ).add_to(marker_cluster)

    m.save(OUTPUT_MAP)
    print(f"Map created: {OUTPUT_MAP}")
    webbrowser.open("file://" + os.path.realpath(OUTPUT_MAP))


if __name__ == "__main__":
    generate_map()

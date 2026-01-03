import folium
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium

# --- Configuration ---
INPUT_FILE = "ryokans_db.csv"
JAPAN_COORDS = [36.2048, 138.2529]


def load_data():
    try:
        # Load data (handling the semicolon separator)
        df = pd.read_csv(INPUT_FILE, sep=";")

        # Ensure coordinates are numeric and drop missing ones
        df = df.dropna(subset=["lat", "lon"])

        # Clean up price (ensure it's int)
        df["price_range_min"] = (
            pd.to_numeric(df["price_range_min"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        df["price_range_max"] = (
            pd.to_numeric(df["price_range_max"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

        return df
    except FileNotFoundError:
        return None


def main():
    st.set_page_config(
        page_title="Ryokan Explorer", layout="wide", page_icon="♨️"
    )

    st.title("♨️ Japan Ryokan Explorer")
    st.markdown("Filter and discover the perfect Onsen Ryokan for your trip.")

    df = load_data()

    if df is None:
        st.error(
            f"Database file `{INPUT_FILE}` not found. Please run the scraper first."
        )
        return

    if df.empty:
        st.warning(
            "No Ryokans found with GPS coordinates. Please run the GPS fetcher script."
        )
        return

    # --- Sidebar Filters ---
    st.sidebar.header("Filter Options")

    # 1. Price Filter (Double-ended slider)
    # Find sensible defaults from data
    min_data_price = int(df["price_range_min"].min())
    max_data_price = int(df["price_range_max"].max())

    price_range = st.sidebar.slider(
        "💰 Price Range (Yen/Night)",
        min_value=0,
        max_value=150000,  # Cap at 150k for slider usability
        value=(10000, 50000),
        step=1000,
    )

    # 2. Rating Filter (Single slider)
    min_rating = st.sidebar.slider(
        "⭐ Min TripAdvisor Rating",
        min_value=0.0,
        max_value=5.0,
        value=3.5,
        step=0.1,
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Amenities")

    # 3. Toggles for Baths
    # "True" means we filter to keep ONLY those that have it.
    # "False" means we don't care (show all).
    show_open_air_room = st.sidebar.toggle(
        "Rooms with Open-Air Bath", value=False
    )
    show_rental_open = st.sidebar.toggle(
        "Private Rental Open-Air Bath", value=False
    )
    show_rental_indoor = st.sidebar.toggle(
        "Private Rental Indoor Bath", value=False
    )
    show_rental_both = st.sidebar.toggle(
        "Private Rental (Both Types)", value=False
    )

    # --- Filtering Logic ---
    filtered_df = df.copy()

    # Filter Price: Keep if the ryokan's min price is within the user's selected range
    # (Logic: Is the ryokan affordable within the selected budget?)
    filtered_df = filtered_df[
        (filtered_df["price_range_min"] >= price_range[0])
        & (filtered_df["price_range_min"] <= price_range[1])
    ]

    # Filter Rating
    filtered_df = filtered_df[filtered_df["tripadvisor_rating"] >= min_rating]

    # Filter Amenities (If toggle is ON, column must be > 0 or True)
    if show_open_air_room:
        filtered_df = filtered_df[filtered_df["room_with_open_air_bath"] > 0]

    if show_rental_open:
        filtered_df = filtered_df[filtered_df["rental_open_air_tubs"] == True]

    if show_rental_indoor:
        filtered_df = filtered_df[filtered_df["rental_indoor_tubs"] == True]

    if show_rental_both:
        filtered_df = filtered_df[
            filtered_df["rental_both_indoor_outdoor_tubs"] == True
        ]

    # --- Map Generation ---
    st.markdown(
        f"**Found {len(filtered_df)} Ryokans matching your criteria.**"
    )

    m = folium.Map(
        location=JAPAN_COORDS, zoom_start=5, tiles="CartoDB positron"
    )
    Fullscreen().add_to(m)
    marker_cluster = MarkerCluster().add_to(m)

    for _, row in filtered_df.iterrows():
        # Dynamic Icon Color based on Price
        color = "green"
        if row["price_range_min"] > 100000:
            color = "black"
        elif row["price_range_min"] > 60000:
            color = "purple"
        elif row["price_range_min"] > 30000:
            color = "orange"

        # Create Popup
        # Note: We use basic HTML here because Folium/Streamlit integration handles it well
        popup_html = f"""
        <b>{row['name']}</b><br>
        Price: ¥{row['price_range_min']:,}<br>
        Rating: {row['tripadvisor_rating']}⭐<br>
        <a href="{row['url']}" target="_blank">View Details</a>
        """

        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=f"{row['name']} (¥{row['price_range_min']:,})",
            icon=folium.Icon(color=color, icon="hot-tub-person", prefix="fa"),
        ).add_to(marker_cluster)

    # Display Map
    st_folium(m, width=1200, height=600)

    # --- Data Table View ---
    with st.expander("See details in list view"):
        # Show specific relevant columns
        cols = [
            "name",
            "location",
            "price_range_min",
            "tripadvisor_rating",
            "url",
        ]
        st.dataframe(
            filtered_df[cols].sort_values(
                by="tripadvisor_rating", ascending=False
            ),
            column_config={
                "url": st.column_config.LinkColumn("Link"),
                "price_range_min": st.column_config.NumberColumn(
                    "Price (¥)", format="¥%d"
                ),
            },
            use_container_width=True,
        )


if __name__ == "__main__":
    main()

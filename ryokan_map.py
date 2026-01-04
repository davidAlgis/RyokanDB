import folium
import pandas as pd
import requests
import streamlit as st
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium

# --- Configuration ---
INPUT_FILE = "ryokans_db.csv"
JAPAN_COORDS = [36.2048, 138.2529]

# Fallback rates in case API fails
FALLBACK_RATES = {
    "JPY": 1.0,
    "USD": 0.0067,  # approx 1 USD = 150 JPY
    "EUR": 0.0062,  # approx 1 EUR = 160 JPY
}

SYMBOLS = {"JPY": "¥", "USD": "$", "EUR": "€"}


@st.cache_data(ttl=3600)
def fetch_exchange_rates():
    """
    Fetches real-time exchange rates with JPY as the base.
    """
    try:
        url = "https://open.er-api.com/v6/latest/JPY"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        rates = {
            "JPY": 1.0,
            "USD": data["rates"]["USD"],
            "EUR": data["rates"]["EUR"],
        }
        return rates
    except Exception as e:
        print(f"⚠️ API Error (using fallback rates): {e}")
        return FALLBACK_RATES


@st.cache_data
def load_data():
    try:
        df = pd.read_csv(INPUT_FILE, sep=";")
        df = df.dropna(subset=["lat", "lon"])
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

    # 1. Load Data
    df = load_data()

    # 2. Fetch Rates
    rates = fetch_exchange_rates()

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

    # Currency Selector
    currency = st.sidebar.selectbox("Currency", ["JPY", "USD", "EUR"])
    current_rate = rates[currency]
    symbol = SYMBOLS[currency]

    if currency != "JPY":
        st.sidebar.caption(
            f"ℹ️ Live Rate: 10,000 JPY ≈ {10000 * current_rate:.2f} {currency}"
        )

    # Dynamic Price Sliders
    min_actual_price_converted = int(
        df["price_range_min"].min() * current_rate
    )
    max_actual_price_converted = int(
        df["price_range_max"].max() * current_rate
    )

    slider_max = max_actual_price_converted + (
        5000 * current_rate if currency == "JPY" else 100
    )

    price_range = st.sidebar.slider(
        f"💰 Price Range ({currency}/Night)",
        min_value=min_actual_price_converted,
        max_value=int(slider_max),
        value=(
            min_actual_price_converted,
            int(max_actual_price_converted * 0.5),
        ),
        step=1000 if currency == "JPY" else 10,
    )

    # Rating Filter
    min_rating = st.sidebar.slider(
        "⭐ Min TripAdvisor Rating",
        min_value=0.0,
        max_value=5.0,
        value=3.5,
        step=0.1,
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Amenities")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        show_open_air_room = st.toggle("Room w/ Open-Air Bath", value=False)
        show_rental_open = st.toggle("Private Rental Outdoor", value=False)
    with col2:
        show_rental_indoor = st.toggle("Private Rental Indoor", value=False)
        show_rental_both = st.toggle("Private Rental Both", value=False)

    # --- Filtering Logic ---
    filtered_df = df.copy()

    min_filter_jpy = price_range[0] / current_rate
    max_filter_jpy = price_range[1] / current_rate

    filtered_df = filtered_df[
        (filtered_df["price_range_min"] >= min_filter_jpy)
        & (filtered_df["price_range_min"] <= max_filter_jpy)
    ]

    filtered_df = filtered_df[filtered_df["tripadvisor_rating"] >= min_rating]

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
        display_price = int(row["price_range_min"] * current_rate)

        price_jpy = row["price_range_min"]
        color = "green"
        if price_jpy > 100000:
            color = "black"
        elif price_jpy > 60000:
            color = "purple"
        elif price_jpy > 30000:
            color = "orange"

        popup_html = f"""
        <div style="font-family:sans-serif; min-width:180px">
            <b>{row['name']}</b><br>
            Price: {symbol}{display_price:,}<br>
            Rating: {row['tripadvisor_rating']}⭐<br>
            <a href="{row['url']}" target="_blank">View Details</a>
        </div>
        """

        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{row['name']} ({symbol}{display_price:,})",
            icon=folium.Icon(color=color, icon="hot-tub-person", prefix="fa"),
        ).add_to(marker_cluster)

    # Display Map
    # FIX 1: Updated st_folium arguments
    st_folium(m, height=600, width="stretch")

    # --- Data Table View ---
    with st.expander("See details in list view"):
        display_df = filtered_df.copy()
        display_df["display_price"] = (
            display_df["price_range_min"] * current_rate
        ).astype(int)

        cols = [
            "name",
            "location",
            "display_price",
            "tripadvisor_rating",
            "url",
        ]

        # FIX 2: Updated st.dataframe arguments
        st.dataframe(
            display_df[cols].sort_values(
                by="tripadvisor_rating", ascending=False
            ),
            column_config={
                "url": st.column_config.LinkColumn("Link"),
                "display_price": st.column_config.NumberColumn(
                    f"Price ({symbol})", format=f"{symbol}%d"
                ),
            },
            width="stretch",
        )


if __name__ == "__main__":
    main()

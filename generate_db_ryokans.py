import random
import re
import time
import unicodedata

import pandas as pd
import requests
from bs4 import BeautifulSoup
# Import our new GPS helper
from ryokan_gps import RyokanLocator
from tqdm import tqdm

# --- Configuration ---
BASE_URL = "https://selected-ryokan.com"
LISTING_URL_TEMPLATE = "https://selected-ryokan.com/ryokan/page/{}"
TOTAL_PAGES = 54
OUTPUT_FILE = "ryokans_db.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Initialize the GPS Locator once
locator = RyokanLocator()


def clean_text(text):
    """
    Normalizes text to ASCII, removing accents and special characters
    like non-breaking spaces (<0xa0>).
    """
    if not text:
        return ""

    # 1. Explicitly replace non-breaking spaces with standard spaces
    #    (Prevents words from sticking together when non-ascii chars are stripped)
    text = text.replace("\xa0", " ")

    # 2. Normalize Unicode characters
    #    'NFKD' decomposes characters (e.g., 'é' becomes 'e' + '´')
    text = unicodedata.normalize("NFKD", text)

    # 3. Encode to ASCII, ignoring errors (strips the '´' and other non-ascii chars)
    text = text.encode("ascii", "ignore").decode("ascii")

    # 4. Standard whitespace cleanup
    text = text.replace("\n", " ").replace("\r", "").replace("\t", " ")

    # 5. Remove multiple spaces and strip
    cleaned = re.sub(" +", " ", text)

    return cleaned.strip()


def get_ryokan_details(url):
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        # 1. Name
        h1 = soup.find("h1")
        name = clean_text(h1.text) if h1 else "Unknown"

        # 2. Location
        addr_tag = soup.select_one(".txt-address")
        location = "Unknown"
        if addr_tag:
            raw_addr = addr_tag.text.split("Show map")[0]
            location = clean_text(raw_addr)

        # 3. Price Range
        price_min = 0
        price_max = 0
        price_section = soup.select_one("#tit-price")
        if price_section:
            price_div = price_section.find_parent("div")
            price_span = (
                price_div.find("p").find("span") if price_div else None
            )
            if price_span:
                price_text = price_span.text.replace(",", "")
                prices = re.findall(r"\d+", price_text)
                if len(prices) >= 2:
                    price_min = int(prices[0])
                    price_max = int(prices[1])
                elif len(prices) == 1:
                    price_min = int(prices[0])
                    price_max = int(prices[0])

        # 4. Room with open-air bath
        rooms_count = 0
        content_div = soup.select_one(".ryokan-text .content")
        if content_div:
            text_content = content_div.get_text()
            match = re.search(
                r"Rooms with open-air.*?:.*?(\d+)", text_content, re.IGNORECASE
            )
            if match:
                rooms_count = int(match.group(1))
            else:
                private_sec = soup.select_one("#tit-private-use")
                if private_sec:
                    dl = private_sec.find_parent("div").find("dl")
                    if dl and "Available" in dl.text:
                        rooms_count = 1

        # 5. Rental Tubs
        rental_open = False
        rental_indoor = False
        rental_both = False

        detail_privates = soup.select(".detail-private")
        for div in detail_privates:
            header = div.find("h3")
            if header and "Rental" in header.text:
                dls = div.find_all("dl")
                for dl in dls:
                    dt = dl.find("dt").text.lower()
                    dd = dl.find("dd").text.strip()
                    count = 0
                    if dd.isdigit():
                        count = int(dd)

                    if "open-air tubs" in dt and "indoor" not in dt:
                        rental_open = count > 0
                    elif "indoor tubs" in dt and "open-air" not in dt:
                        rental_indoor = count > 0
                    elif "indoor and outdoor" in dt:
                        rental_both = count > 0

        # 6. TripAdvisor Rating (UPDATED)
        rating = 0.0
        # 1. Find the iframe that holds the widget
        ta_iframe = soup.find(
            "iframe", src=re.compile(r"tripadvisor\.com/WidgetEmbed")
        )

        if ta_iframe:
            widget_src = ta_iframe.get("src")
            # Handle protocol-relative URLs (e.g., //www.tripadvisor...)
            if widget_src.startswith("//"):
                widget_src = "https:" + widget_src

            try:
                # 2. Fetch the content of the widget iframe
                # We use a short timeout so we don't hang if TA is slow
                widget_response = requests.get(
                    widget_src, headers=HEADERS, timeout=3
                )
                if widget_response.status_code == 200:
                    widget_soup = BeautifulSoup(
                        widget_response.content, "html.parser"
                    )

                    # 3. Find the image INSIDE the widget HTML
                    ta_img = widget_soup.find(
                        "img", alt=re.compile(r"of 5 bubbles")
                    )
                    if ta_img:
                        alt_text = ta_img["alt"]
                        match = re.search(r"([\d\.]+)", alt_text)
                        if match:
                            rating = float(match.group(1))
            except Exception:
                # If scraping the widget fails, we silently default to 0.0
                pass

        # 7. Tags
        tags = []
        tags_section = soup.select_one(".ryokan-category.tags")
        if tags_section:
            for a in tags_section.find_all("a"):
                tags.append(clean_text(a.text))

        # 8. Description
        description = ""
        if content_div:
            p_tag = content_div.find("p")
            if p_tag:
                description = clean_text(p_tag.text)

        # 9. Transportation
        transport = ""
        trans_tag = soup.select_one(".txt-Transportation")
        if trans_tag:
            parent_article = trans_tag.find_parent("article")
            if parent_article:
                ps = parent_article.find_all("p")
                trans_lines = [
                    clean_text(p.text)
                    for p in ps
                    if p.text.strip().startswith("(")
                ]
                transport = " | ".join(trans_lines)

        # --- GPS Fetch ---
        lat, lon = locator.get_coordinates(name, location)

        return {
            "name": name,
            "location": location,
            "price_range_min": price_min,
            "price_range_max": price_max,
            "room_with_open_air_bath": rooms_count,
            "rental_open_air_tubs": rental_open,
            "rental_indoor_tubs": rental_indoor,
            "rental_both_indoor_outdoor_tubs": rental_both,
            "tripadvisor_rating": rating,
            "tags": str(tags),
            "description": description,
            "transportation": transport,
            "lat": lat,
            "lon": lon,
            "url": url,
        }

    except Exception as e:
        tqdm.write(f"Error parsing {url}: {e}")
        return None


def main():
    all_ryokans = []

    print("Starting scraping process (including GPS fetching)...")

    with tqdm(total=TOTAL_PAGES, desc="Scraping Pages", unit="page") as pbar:
        for page_num in range(1, TOTAL_PAGES + 1):
            url = LISTING_URL_TEMPLATE.format(page_num)

            try:
                response = requests.get(url, headers=HEADERS)
                if response.status_code != 200:
                    tqdm.write(f"Failed to load page {page_num}")
                    pbar.update(1)
                    continue

                soup = BeautifulSoup(response.content, "html.parser")
                articles = soup.find_all("article")

                urls_to_scrape = []
                for art in articles:
                    a_tag = art.find("a", class_="box-link")
                    if a_tag:
                        link = a_tag["href"]
                        if (
                            "/ryokan/" in link
                            and "page/" not in link
                            and "/guide/" not in link
                        ):
                            urls_to_scrape.append(link)

                for link in tqdm(
                    urls_to_scrape,
                    desc=f"Page {page_num} Items",
                    leave=False,
                    unit="ryokan",
                ):
                    details = get_ryokan_details(link)
                    if details:
                        all_ryokans.append(details)
                    # Small delay to be polite, though GPS fetching adds natural delay
                    time.sleep(random.uniform(0.5, 1.0))

            except Exception as e:
                tqdm.write(f"Error on page {page_num}: {e}")

            pbar.update(1)

            # Progressive Save (Optional but safe)
            if page_num % 5 == 0:
                df_temp = pd.DataFrame(all_ryokans)
                df_temp.to_csv(
                    OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig"
                )

    # Final Save
    df = pd.DataFrame(all_ryokans)
    df.to_csv(OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig")

    # Statistics
    found_gps = df["lat"].count()
    print(f"\nDone! Scraped {len(df)} ryokans.")
    print(f"GPS Coordinates found for: {found_gps}/{len(df)} ryokans.")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

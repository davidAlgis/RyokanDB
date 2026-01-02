import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import random

# --- Configuration ---
BASE_URL = "https://selected-ryokan.com"
LISTING_URL_TEMPLATE = "https://selected-ryokan.com/ryokan/page/{}"
TOTAL_PAGES = 54
OUTPUT_FILE = "ryokans_db.csv"

# Headers to mimic a real browser to avoid immediate blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def clean_text(text):
    if text:
        return text.strip().replace('\n', ' ').replace('\r', '')
    return ""

def get_ryokan_details(url):
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 1. Name
        # Usually found in h1 or h2 with class 'canta' or extracted from title
        # Based on snippet, name appears in the listing, but on detail page:
        # We try to grab the first h2 inside 'ryokan-text' or the page title
        h1 = soup.find('h1')
        name = h1.text.strip() if h1 else "Unknown"
        
        # 2. Location
        addr_tag = soup.select_one('.txt-address')
        location = clean_text(addr_tag.text.split('Show map')[0]) if addr_tag else "Unknown"

        # 3. Price Range (Min/Max)
        price_min = 0
        price_max = 0
        price_section = soup.select_one('#tit-price')
        if price_section:
            price_div = price_section.find_parent('div')
            price_span = price_div.find('p').find('span') if price_div else None
            if price_span:
                price_text = price_span.text.replace(',', '')
                prices = re.findall(r'\d+', price_text)
                if len(prices) >= 2:
                    price_min = int(prices[0])
                    price_max = int(prices[1])
                elif len(prices) == 1:
                    price_min = int(prices[0])
                    price_max = int(prices[0])

        # 4. Room with open-air bath (Int)
        # Strategy: Look for specific text in "ryokan-text" section first (e.g., "12 rooms")
        # If not found, check the boolean "Available" table and set to 1 (placeholder)
        rooms_count = 0
        content_div = soup.select_one('.ryokan-text .content')
        if content_div:
            # Look for pattern: "Rooms with open-air hot spring baths available: X rooms"
            text_content = content_div.get_text()
            match = re.search(r'Rooms with open-air.*?:.*?(\d+)', text_content, re.IGNORECASE)
            if match:
                rooms_count = int(match.group(1))
            else:
                # Fallback to the table
                private_sec = soup.select_one('#tit-private-use')
                if private_sec:
                    dl = private_sec.find_parent('div').find('dl')
                    if dl and "Available" in dl.text:
                        rooms_count = 1 # Indicates available, but count unknown

        # 5. Rental Tubs (Booleans)
        rental_open = False
        rental_indoor = False
        rental_both = False
        
        # Find the specific section for "Rental hot spring baths for private use"
        # In snippet 2, there are two #tit-private-use. We need the second one usually, 
        # or we iterate all .detail-private divs
        detail_privates = soup.select('.detail-private')
        for div in detail_privates:
            header = div.find('h3')
            if header and "Rental" in header.text:
                dls = div.find_all('dl')
                for dl in dls:
                    dt = dl.find('dt').text.lower()
                    dd = dl.find('dd').text.strip()
                    count = 0
                    if dd.isdigit():
                        count = int(dd)
                    
                    if "open-air tubs" in dt and "indoor" not in dt:
                        rental_open = count > 0
                    elif "indoor tubs" in dt and "open-air" not in dt:
                        rental_indoor = count > 0
                    elif "indoor and outdoor" in dt:
                        rental_both = count > 0

        # 6. TripAdvisor Rating
        rating = 0.0
        # Look for img with alt "X of 5 bubbles"
        ta_img = soup.find('img', alt=re.compile(r'of 5 bubbles'))
        if ta_img:
            alt_text = ta_img['alt']
            match = re.search(r'([\d\.]+)', alt_text)
            if match:
                rating = float(match.group(1))

        # 7. Tags
        tags = []
        tags_section = soup.select_one('.ryokan-category.tags')
        if tags_section:
            for a in tags_section.find_all('a'):
                tags.append(a.text.strip())

        # 8. Description
        # Grab first paragraph of content
        description = ""
        if content_div:
            p_tag = content_div.find('p')
            if p_tag:
                description = clean_text(p_tag.text)

        # 9. Transportation
        transport = ""
        trans_tag = soup.select_one('.txt-Transportation')
        if trans_tag:
            # Get siblings after this p tag until the end of article or next section
            # Simplified: grab the text of the parent article
            parent_article = trans_tag.find_parent('article')
            if parent_article:
                # regex to find (1)... (2)...
                full_text = parent_article.get_text()
                # Try to extract text occurring after "Transportation" header logic
                # For now, let's grab the whole text of paragraphs starting with (
                ps = parent_article.find_all('p')
                trans_lines = [p.text.strip() for p in ps if p.text.strip().startswith('(')]
                transport = " | ".join(trans_lines)

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
            "tags": tags, # list
            "description": description,
            "transportation": transport,
            "url": url
        }

    except Exception as e:
        print(f"Error parsing {url}: {e}")
        return None

def main():
    all_ryokans = []
    
    print("Starting scraping process...")
    
    for page_num in range(1, TOTAL_PAGES + 1):
        print(f"Scraping Listing Page {page_num}/{TOTAL_PAGES}...")
        url = LISTING_URL_TEMPLATE.format(page_num)
        
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"Failed to load page {page_num}")
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all articles
            articles = soup.find_all('article')
            
            for art in articles:
                # Find the link
                a_tag = art.find('a', class_='box-link')
                if not a_tag:
                    continue
                    
                link = a_tag['href']
                
                # Filter: We only want Ryokan details, not "Guide" pages
                # Guides usually have /guide/ in URL, Ryokans have /ryokan/ (and not /page/)
                if "/guide/" in link:
                    continue
                if "/ryokan/" in link and "page/" not in link:
                    # Check duplicate processing if needed, but list logic usually sufficient
                    print(f"  > Fetching details for: {link}")
                    details = get_ryokan_details(link)
                    if details:
                        all_ryokans.append(details)
                    
                    # Be polite to the server
                    time.sleep(random.uniform(0.5, 1.5))
                    
        except Exception as e:
            print(f"Error on page {page_num}: {e}")

    # Create DataFrame
    df = pd.DataFrame(all_ryokans)
    
    # Save to CSV
    # Sep semicolon specified in prompt logic implies CSV structure, 
    # but standard CSV uses comma. I will use comma default, but if you strictly
    # need semicolon, change sep=';' below.
    df.to_csv(OUTPUT_FILE, sep=';', index=False, encoding='utf-8-sig')
    print(f"Done! Scraped {len(df)} ryokans. Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
import requests
from bs4 import BeautifulSoup
import json
import asyncio
import os
import random
import re
import threading
from urllib.parse import urljoin
from flask import Flask

# --- RENDER WEB SERVER SETUP ---
app = Flask(__name__)

# --- HARDCODED CONFIGURATION ---
BASE_URL = "https://jiji.co.ke"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
MIN_ADS = 50          # Minimum ads to qualify as a "Whale"
WHALES_TARGET = 3     # Number of sellers to harvest per run
PROD_LIMIT = 40       # Products to scrape per seller
DATA_FOLDER = "scraped_data"

# --- SCRAPER LOGIC ---

def clean_biz_name(raw_name):
    """Cleans Jiji business names from 'Verified' or '5y+' badges."""
    match = re.search(r'(\d+\+?\s*(year|month|day))|Verified', raw_name, re.IGNORECASE)
    return raw_name[:match.start()].strip() if match else raw_name.strip()

async def parse_deep_attributes(product_url):
    """Scrapes internal attributes and descriptions for a product."""
    try:
        res = await asyncio.to_thread(requests.get, product_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        attr_blocks = soup.select(".b-render-attr")
        attributes = []
        for b in attr_blocks:
            key = b.select_one(".b-render-attr__name")
            val = b.select_one(".qa-advert-attribute")
            if key and val:
                attributes.append({"key": key.get_text(strip=True), "value": val.get_text(strip=True)})
        desc_el = soup.select_one(".b-advert__description-text")
        description = desc_el.get_text(strip=True) if desc_el else ""
        return attributes, description
    except:
        return [], ""

async def harvest_inventory(seller_url, business_name, limit, no_ads):
    """Scrapes products from a seller's page using pagination logic."""
    safe_name = "".join(x for x in business_name if x.isalnum() or x in " -_").strip()
    base_dir = os.path.join(DATA_FOLDER, "businesses", safe_name)
    img_dir = os.path.join(base_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    products_data = []
    page = 1
    base_inventory_url = seller_url.split('?')[0] 

    while len(products_data) < limit:
        target_page_url = f"{base_inventory_url}?page={page}"
        print(f"      > Harvesting Page {page}: {target_page_url}")
        
        try:
            res = await asyncio.to_thread(requests.get, target_page_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select('.b-seller-advert, .masonry-item, .qa-advert-list-item, .b-list-advert__item-wrapper')
            
            if not items: break 

            new_items_found = 0
            for item in items:
                if len(products_data) >= limit: break
                
                title_tag = item.select_one('.b-advert-title-inner, .qa-advert-list-item-title')
                price_tag = item.select_one('.qa-advert-price, .b-advert-price, .b-seller-advert__price')
                a_tag = item.find('a', href=True)
                
                if not title_tag or not a_tag: continue

                p_link = urljoin(BASE_URL, a_tag['href'])
                p_price = price_tag.get_text(strip=True).replace('KSh', '').replace(',', '').strip() if price_tag else "0"
                
                img_tag = item.find('img')
                img_url = img_tag.get('src') or img_tag.get('data-src') if img_tag else None
                index = len(products_data) + 1
                
                if img_url:
                    try:
                        img_res = await asyncio.to_thread(requests.get, img_url, headers=HEADERS, timeout=10)
                        with open(os.path.join(img_dir, f"image{index}.jpg"), 'wb') as f: f.write(img_res.content)
                    except: pass

                attrs, desc = await parse_deep_attributes(p_link)

                products_data.append({
                    "id": index, 
                    "title": title_tag.get_text(strip=True),
                    "price": p_price,
                    "image_path": f"images/image{index}.jpg", 
                    "no_ads": no_ads,
                    "attributes": attrs,
                    "description": desc,
                    "link": p_link
                })
                new_items_found += 1
            
            if new_items_found == 0: break
            page += 1
            await asyncio.sleep(random.uniform(1, 2)) 
        except Exception as e:
            print(f"      [!] Error during harvest: {e}")
            break

    with open(os.path.join(base_dir, "products.json"), 'w', encoding='utf-8') as f: 
        json.dump(products_data, f, indent=4, ensure_ascii=False)
    return len(products_data)

async def start_hunt():
    """Main discovery loop: picks a random category and finds 'Whales'."""
    if os.path.exists("stage1.json"):
        with open("stage1.json", "r") as f:
            categories = json.load(f)
    else:
        categories = ["/electronics", "/home-garden", "/cars"]
    
    selected_cat = random.choice(categories)
    print(f"[*] Chosen Category: {selected_cat}")

    found, page, seen = 0, 1, set()

    while found < WHALES_TARGET:
        cat_url = f"{BASE_URL}{selected_cat}?page={page}"
        print(f"[*] Scanning Page {page}...")
        
        try:
            res = await asyncio.to_thread(requests.get, cat_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            links = [a["href"] for a in soup.find_all("a", href=True) if ".html" in a["href"]]

            if not links: break

            for link in links:
                if found >= WHALES_TARGET: break
                p_url = urljoin(BASE_URL, link)
                
                try:
                    p_res = await asyncio.to_thread(requests.get, p_url, headers=HEADERS, timeout=10)
                    p_soup = BeautifulSoup(p_res.text, "html.parser")
                    s_tag = p_soup.find("a", href=lambda x: x and ("/sellerpage" in x or "/shop/" in x))

                    if s_tag:
                        s_url = urljoin(BASE_URL, s_tag["href"])
                        if s_url in seen: continue
                        seen.add(s_url)

                        s_res = await asyncio.to_thread(requests.get, s_url, headers=HEADERS, timeout=10)
                        s_soup = BeautifulSoup(s_res.text, "html.parser")
                        ads_count = sum(int(''.join(filter(str.isdigit, e.get_text())) or 0) for e in s_soup.find_all("div", class_="b-seller-top-categories__item-center"))

                        if ads_count >= MIN_ADS:
                            name_tag = s_soup.find("div", class_="b-seller-info-block__name") or s_soup.find("h1")
                            b_name = clean_biz_name(name_tag.get_text(strip=True)) if name_tag else "Store"
                            print(f"[WHALE FOUND] {b_name} with {ads_count} ads.")
                            
                            count = await harvest_inventory(s_url, b_name, PROD_LIMIT, ads_count)
                            print(f"   -> Saved {count} items for {b_name}")
                            found += 1
                except: continue
            page += 1
        except: break

    print("[FINISH] Hunt Session Complete.")

# --- FLASK ROUTES ---

@app.route('/')
def home():
    return "Dooka Scraper is Active.", 200

@app.route('/run')
def trigger():
    """Triggers the scraper in a background thread."""
    threading.Thread(target=lambda: asyncio.run(start_hunt())).start()
    return "Scraper hunt started in the background!", 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

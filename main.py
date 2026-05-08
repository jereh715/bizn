import requests
from bs4 import BeautifulSoup
import json
import asyncio
import os
import random
import re
import threading
from urllib.parse import urljoin
from flask import Flask, request

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_URL = "https://jiji.co.ke"
# Updated Headers to look like a modern Chrome browser to avoid 403 Forbidden
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}
MIN_ADS = 15          # Lowered for testing; change back to 50 when confirmed working
WHALES_TARGET = 1     # Start small to verify the process
PROD_LIMIT = 20       
DATA_FOLDER = "scraped_data"

# --- UTILITIES ---

def clean_biz_name(raw_name):
    match = re.search(r'(\d+\+?\s*(year|month|day))|Verified', raw_name, re.IGNORECASE)
    return raw_name[:match.start()].strip() if match else raw_name.strip()

async def parse_deep_attributes(product_url):
    try:
        res = await asyncio.to_thread(requests.get, product_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        attributes = []
        for b in soup.select(".b-render-attr"):
            key = b.select_one(".b-render-attr__name")
            val = b.select_one(".qa-advert-attribute")
            if key and val:
                attributes.append({"key": key.get_text(strip=True), "value": val.get_text(strip=True)})
        desc_el = soup.select_one(".b-advert__description-text")
        return attributes, desc_el.get_text(strip=True) if desc_el else ""
    except: return [], ""

async def harvest_inventory(seller_url, business_name, limit, no_ads):
    safe_name = "".join(x for x in business_name if x.isalnum() or x in " -_").strip()
    base_dir = os.path.join(DATA_FOLDER, "businesses", safe_name)
    os.makedirs(base_dir, exist_ok=True)

    products_data = []
    page = 1
    while len(products_data) < limit:
        url = f"{seller_url.split('?')[0]}?page={page}"
        print(f"      > Scraping Page {page}")
        try:
            res = await asyncio.to_thread(requests.get, url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.select('.b-seller-advert, .qa-advert-list-item, .b-list-advert__item-wrapper')
            if not items: break
            for item in items:
                if len(products_data) >= limit: break
                a_tag = item.find('a', href=True)
                if not a_tag: continue
                p_link = urljoin(BASE_URL, a_tag['href'])
                attrs, desc = await parse_deep_attributes(p_link)
                products_data.append({"title": a_tag.get_text(strip=True), "attributes": attrs, "description": desc})
            page += 1
            await asyncio.sleep(2)
        except: break

    with open(os.path.join(base_dir, "products.json"), 'w') as f:
        json.dump(products_data, f, indent=4)
    return len(products_data)

async def start_hunt():
    if os.path.exists("stage1.json"):
        with open("stage1.json", "r") as f: categories = json.load(f)
    else: categories = ["/mobile-phones"]
    
    selected_cat = random.choice(categories)
    print(f"[*] Starting Hunt: {selected_cat}")
    found, page = 0, 1

    while found < WHALES_TARGET:
        cat_url = f"{BASE_URL}{selected_cat}?page={page}"
        try:
            res = await asyncio.to_thread(requests.get, cat_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            links = [a["href"] for a in soup.find_all("a", href=True) if ".html" in a["href"]]
            if not links: break
            for link in links:
                if found >= WHALES_TARGET: break
                p_res = await asyncio.to_thread(requests.get, urljoin(BASE_URL, link), headers=HEADERS, timeout=10)
                s_tag = BeautifulSoup(p_res.text, "html.parser").find("a", href=lambda x: x and ("/sellerpage" in x or "/shop/" in x))
                if s_tag:
                    s_url = urljoin(BASE_URL, s_tag["href"])
                    s_res = await asyncio.to_thread(requests.get, s_url, headers=HEADERS, timeout=10)
                    s_soup = BeautifulSoup(s_res.text, "html.parser")
                    ads = sum(int(''.join(filter(str.isdigit, e.get_text())) or 0) for e in s_soup.find_all("div", class_="b-seller-top-categories__item-center"))
                    if ads >= MIN_ADS:
                        name = s_soup.find("h1").get_text(strip=True) if s_soup.find("h1") else "Store"
                        print(f"[WHALE FOUND] {name} ({ads} ads)")
                        await harvest_inventory(s_url, name, PROD_LIMIT, ads)
                        found += 1
            page += 1
        except: break
    print("[FINISH] Done.")

# --- ROUTES ---

@app.route('/')
def home(): return "Active", 200

@app.route('/run')
def trigger():
    threading.Thread(target=lambda: asyncio.run(start_hunt())).start()
    return "Started", 202

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

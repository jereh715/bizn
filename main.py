import requests
from bs4 import BeautifulSoup
import json
import asyncio
import os
import random
import re
from urllib.parse import urljoin

# --- HARDCODED CONFIGURATION ---
BASE_URL = "https://jiji.co.ke"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
MIN_ADS = 50          # Only harvest sellers with 50+ ads
WHALES_TARGET = 3     # How many whales to find per run
PROD_LIMIT = 40       # How many products to scrape per whale
DATA_FOLDER = "scraped_data"

def clean_biz_name(raw_name):
    # Removes "Verified" or "5y+" badges from the business name
    match = re.search(r'(\d+\+?\s*(year|month|day))|Verified', raw_name, re.IGNORECASE)
    return raw_name[:match.start()].strip() if match else raw_name.strip()

async def parse_deep_attributes(product_url):
    # Scrapes the internal attributes and description of a specific product
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
    # Fixed pagination logic to scrape seller products across multiple pages
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
                
                # Image Downloading
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
        except: break

    # Save to JSON
    with open(os.path.join(base_dir, "products.json"), 'w', encoding='utf-8') as f: 
        json.dump(products_data, f, indent=4, ensure_ascii=False)
    return len(products_data)

async def start_hunt():
    # 1. Select random category from stage1.json
    if os.path.exists("stage1.json"):
        with open("stage1.json", "r") as f:
            categories = json.load(f)
    else:
        categories = ["/electronics", "/home-garden", "/cars"]
    
    selected_cat = random.choice(categories)
    print(f"[*] Chosen Category: {selected_cat}")

    found, page, seen = 0, 1, set()

    # 2. Main Discovery Loop
    while found < WHALES_TARGET:
        cat_url = f"{BASE_URL}{selected_cat}?page={page}"
        print(f"[*] Scanning {selected_cat} - Page {page}")
        
        try:
            res = await asyncio.to_thread(requests.get, cat_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            links = [a["href"] for a in soup.find_all("a", href=True) if ".html" in a["href"]]

            if not links: break

            for link in links:
                if found >= WHALES_TARGET: break
                p_url = urljoin(BASE_URL, link)
                
                try:
                    # Get the product page to find the seller link
                    p_res = await asyncio.to_thread(requests.get, p_url, headers=HEADERS, timeout=10)
                    p_soup = BeautifulSoup(p_res.text, "html.parser")
                    s_tag = p_soup.find("a", href=lambda x: x and ("/sellerpage" in x or "/shop/" in x))

                    if s_tag:
                        s_url = urljoin(BASE_URL, s_tag["href"])
                        if s_url in seen: continue
                        seen.add(s_url)

                        # Check for Whale Status (50+ ads)
                        s_res = await asyncio.to_thread(requests.get, s_url, headers=HEADERS, timeout=10)
                        s_soup = BeautifulSoup(s_res.text, "html.parser")
                        ads_count = sum(int(''.join(filter(str.isdigit, e.get_text())) or 0) for e in s_soup.find_all("div", class_="b-seller-top-categories__item-center"))

                        if ads_count >= MIN_ADS:
                            name_tag = s_soup.find("div", class_="b-seller-info-block__name") or s_soup.find("h1")
                            b_name = clean_biz_name(name_tag.get_text(strip=True)) if name_tag else "Store"
                            print(f"[WHALE FOUND] {b_name} with {ads_count} ads. Harvesting...")
                            
                            count = await harvest_inventory(s_url, b_name, PROD_LIMIT, ads_count)
                            print(f"   -> Successfully saved {count} items for {b_name}")
                            found += 1
                except: continue
            page += 1
        except: break

    print("[FINISH] Hunt Session Complete.")

if __name__ == "__main__":
    asyncio.run(start_hunt())

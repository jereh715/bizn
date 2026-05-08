import asyncio
import os
import json
import random
import re
import threading
from urllib.parse import urljoin
from flask import Flask
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from bs4 import BeautifulSoup

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_URL = "https://jiji.co.ke"
MIN_ADS = 15          # Lowered for testing
WHALES_TARGET = 1     
PROD_LIMIT = 20       
DATA_FOLDER = "scraped_data"

# --- SCRAPER LOGIC ---

def clean_biz_name(raw_name):
    match = re.search(r'(\d+\+?\s*(year|month|day))|Verified', raw_name, re.IGNORECASE)
    return raw_name[:match.start()].strip() if match else raw_name.strip()

async def harvest_inventory(page, seller_url, business_name):
    """Uses the already open Playwright page to scrape the seller's items."""
    safe_name = "".join(x for x in business_name if x.isalnum() or x in " -_").strip()
    base_dir = os.path.join(DATA_FOLDER, "businesses", safe_name)
    os.makedirs(base_dir, exist_ok=True)
    
    products_data = []
    print(f"      > Harvesting: {business_name}")
    
    # Navigate to seller page
    await page.goto(seller_url, wait_until="networkidle")
    
    # Get HTML and parse with BeautifulSoup
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    
    items = soup.select('.b-seller-advert, .qa-advert-list-item, .b-list-advert__item-wrapper')
    
    for item in items[:PROD_LIMIT]:
        title_tag = item.select_one('.b-advert-title-inner, .qa-advert-list-item-title')
        if title_tag:
            products_data.append({
                "title": title_tag.get_text(strip=True),
                "source": "Playwright/Jiji"
            })

    with open(os.path.join(base_dir, "products.json"), 'w') as f:
        json.dump(products_data, f, indent=4)
    
    return len(products_data)

async def start_hunt():
    """The main loop that bypasses Cloudflare and finds sellers."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page)

        # 1. Load Category
        if os.path.exists("stage1.json"):
            with open("stage1.json", "r") as f: categories = json.load(f)
        else:
            categories = ["/mobile-phones"]
        
        selected_cat = random.choice(categories)
        print(f"[*] Starting Hunt: {selected_cat}")

        try:
            # 2. Go to Category Page
            await page.goto(f"{BASE_URL}{selected_cat}", wait_until="networkidle", timeout=60000)
            
            # 3. Find Product Links
            links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                            .map(a => a.href)
                            .filter(href => href.includes('.html'));
            }''')

            if not links:
                print("[!] No links found. Might still be blocked.")
                return

            # 4. Check the first few items for Whales
            for link in links[:5]:
                await page.goto(link, wait_until="networkidle")
                
                # Look for seller link
                seller_link_handle = await page.query_selector('a[href*="/sellerpage"], a[href*="/shop/"]')
                if seller_link_handle:
                    s_url = await seller_link_handle.get_attribute("href")
                    full_s_url = urljoin(BASE_URL, s_url)
                    
                    # For testing, we'll just treat the first seller found as a Whale
                    count = await harvest_inventory(page, full_s_url, "FoundStore")
                    print(f"[*] Saved {count} items.")
                    break

        except Exception as e:
            print(f"[!] Scraper Error: {e}")
        finally:
            await browser.close()
            print("[FINISH] Session Closed.")

# --- FLASK ROUTES ---

@app.route('/')
def home():
    return "Dooka Playwright Scraper is Live", 200

@app.route('/run')
def trigger():
    threading.Thread(target=lambda: asyncio.run(start_hunt())).start()
    return "Background Hunt Started", 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

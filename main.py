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
WHALES_TARGET = 1     
PROD_LIMIT = 20       
DATA_FOLDER = "scraped_data"

# --- SCRAPER LOGIC ---

async def harvest_inventory(page, seller_url, business_name):
    """Scrapes products from a seller's page."""
    safe_name = "".join(x for x in business_name if x.isalnum() or x in " -_").strip()
    base_dir = os.path.join(DATA_FOLDER, "businesses", safe_name)
    os.makedirs(base_dir, exist_ok=True)
    
    products_data = []
    print(f"      > Harvesting: {business_name}")
    
    try:
        await page.goto(seller_url, wait_until="networkidle", timeout=60000)
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        items = soup.select('.b-seller-advert, .qa-advert-list-item, .b-list-advert__item-wrapper')
        
        for item in items[:PROD_LIMIT]:
            title_tag = item.select_one('.b-advert-title-inner, .qa-advert-list-item-title')
            if title_tag:
                products_data.append({
                    "title": title_tag.get_text(strip=True),
                    "scraped_at": "2026-05-08"
                })

        with open(os.path.join(base_dir, "products.json"), 'w') as f:
            json.dump(products_data, f, indent=4)
        return len(products_data)
    except Exception as e:
        print(f"      [!] Harvest Error: {e}")
        return 0

async def start_hunt():
    """Main discovery loop using Playwright Stealth."""
    async with async_playwright() as p:
        # Launch with essential flags for Docker
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth to bypass Cloudflare 'Just a moment'
        await stealth_async(page)

        # Category selection
        if os.path.exists("stage1.json"):
            with open("stage1.json", "r") as f: categories = json.load(f)
        else:
            categories = ["/mobile-phones", "/cars", "/electronics"]
        
        selected_cat = random.choice(categories)
        print(f"[*] Starting Hunt: {selected_cat}")

        try:
            # Step 1: Hit Category Page
            await page.goto(f"{BASE_URL}{selected_cat}", wait_until="networkidle", timeout=60000)
            
            # Step 2: Get links via JS
            links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                            .map(a => a.href)
                            .filter(href => href.includes('.html'));
            }''')

            if not links:
                print("[!] No product links found on page.")
                return

            # Step 3: Check first available seller
            for link in links[:5]:
                print(f"[*] Checking item: {link}")
                await page.goto(link, wait_until="networkidle")
                
                seller_link_handle = await page.query_selector('a[href*="/sellerpage"], a[href*="/shop/"]')
                if seller_link_handle:
                    s_url = await seller_link_handle.get_attribute("href")
                    full_s_url = urljoin(BASE_URL, s_url)
                    
                    count = await harvest_inventory(page, full_s_url, "ScrapedStore")
                    print(f"[*] Successfully saved {count} items.")
                    break

        except Exception as e:
            print(f"[!] Scraper Error: {e}")
        finally:
            await browser.close()
            print("[FINISH] Session Complete.")

# --- FLASK ROUTES ---

@app.route('/')
def home():
    return "Dooka Playwright Scraper is Active", 200

@app.route('/run')
def trigger():
    threading.Thread(target=lambda: asyncio.run(start_hunt())).start()
    return "Background Hunt Started", 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

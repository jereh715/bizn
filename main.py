import asyncio
import os
import json
import random
import re
import threading
from urllib.parse import urljoin
from flask import Flask
from playwright.async_api import async_playwright
import playwright_stealth
from bs4 import BeautifulSoup

# CRITICAL: Tell playwright where the browsers are
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/app/pw-browsers"

app = Flask(__name__)

BASE_URL = "https://jiji.co.ke"
DATA_FOLDER = "scraped_data"

async def harvest_inventory(page, seller_url, business_name):
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
        
        for item in items[:20]:
            title_tag = item.select_one('.b-advert-title-inner, .qa-advert-list-item-title')
            if title_tag:
                products_data.append({"title": title_tag.get_text(strip=True), "scraped_at": "2026-05-08"})

        with open(os.path.join(base_dir, "products.json"), 'w') as f:
            json.dump(products_data, f, indent=4)
        return len(products_data)
    except Exception as e:
        print(f"      [!] Harvest Error: {e}")
        return 0

async def start_hunt():
    async with async_playwright() as p:
        # THE FIX: Added channel="chromium"
        browser = await p.chromium.launch(
            headless=True,
            channel="chromium", 
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await playwright_stealth.stealth_async(page)

        categories = ["/mobile-phones", "/cars", "/electronics"]
        selected_cat = random.choice(categories)
        print(f"[*] Starting Hunt: {selected_cat}")

        try:
            await page.goto(f"{BASE_URL}{selected_cat}", wait_until="networkidle", timeout=60000)
            links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                            .map(a => a.href)
                            .filter(href => href.includes('.html'));
            }''')

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

@app.route('/')
def home():
    return "Dooka Scraper Online", 200

@app.route('/run')
def trigger():
    t = threading.Thread(target=lambda: asyncio.run(start_hunt()))
    t.start()
    return "Background Hunt Started", 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

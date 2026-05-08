import asyncio
import os
import threading
import random
from flask import Flask
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_URL = "https://jiji.co.ke"
DATA_FOLDER = "scraped_data"
os.makedirs(DATA_FOLDER, exist_ok=True)

async def start_hunt():
    """Simplified hunt to just capture raw HTML and bypass complex logic."""
    async with async_playwright() as p:
        print("[*] Launching Browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Stealth is skipped as requested to avoid 'module' errors
        
        categories = ["/mobile-phones", "/cars", "/electronics", "/home-appliances"]
        selected_cat = random.choice(categories)
        target_url = f"{BASE_URL}{selected_cat}"
        
        print(f"[*] Targeting: {target_url}")

        try:
            # Using 'load' instead of 'networkidle' to avoid timeouts on Render
            await page.goto(target_url, wait_until="load", timeout=60000)
            
            # Get the raw HTML content
            html_content = await page.content()
            
            # Save it to a file
            filename = f"debug_{selected_cat.strip('/')}.html"
            filepath = os.path.join(DATA_FOLDER, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"[*] Success! HTML saved to {filepath}")
            print(f"[*] Character count: {len(html_content)}")

        except Exception as e:
            print(f"[!] Scraper Error: {e}")
        finally:
            await browser.close()
            print("[FINISH] Session Complete.")

# --- FLASK WEB SERVER ---

@app.route('/')
def home():
    return "Dooka HTML Grabber is Active", 200

@app.route('/run')
def trigger():
    """Endpoint to trigger the HTML grab in the background."""
    t = threading.Thread(target=lambda: asyncio.run(start_hunt()))
    t.start()
    return "HTML Grab Started. Check logs.", 202

# New route to see if we actually got the data
@app.route('/view')
def view():
    files = os.listdir(DATA_FOLDER)
    return {"files_in_storage": files}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

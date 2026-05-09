import asyncio
import os
import threading
import random
from flask import Flask, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_URL = "https://jiji.co.ke"
DATA_FOLDER = "scraped_data"
os.makedirs(DATA_FOLDER, exist_ok=True)

async def start_hunt():
    """Captures HTML while attempting to mimic a human to bypass Cloudflare."""
    async with async_playwright() as p:
        print("[*] Launching Browser...")
        # We add more flags to the browser launch to look less 'automated'
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled" # Helps hide the 'bot' flag
            ]
        )
        
        # We define a specific 'Human' context
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
        )
        
        page = await context.new_page()

        # Extra headers to simulate a real request from Google
        await page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://www.google.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site"
        })

        categories = ["/mobile-phones", "/cars", "/electronics", "/home-appliances"]
        selected_cat = random.choice(categories)
        target_url = f"{BASE_URL}{selected_cat}"
        
        print(f"[*] Targeting: {target_url}")

        try:
            # 1. Navigate to the page
            await page.goto(target_url, wait_until="load", timeout=60000)
            
            # 2. THE WAITING GAME: Cloudflare challenges often take 5-8 seconds to resolve
            print("[*] Page loaded. Waiting 8 seconds for security checks to settle...")
            await asyncio.sleep(8) 
            
            # 3. Check the page title to see if we passed
            title = await page.title()
            print(f"[*] Current Page Title: {title}")
            
            if "Cloudflare" in title or "Verify" in title or "Just a moment" in title:
                print("[!] ALERT: Still stuck on security verification page.")
            else:
                print("[SUCCESS] Seemingly bypassed the challenge.")

            # 4. Save the content
            html_content = await page.content()
            filename = f"debug_{selected_cat.strip('/')}.html"
            filepath = os.path.join(DATA_FOLDER, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"[*] HTML saved to {filepath}")
            print(f"[*] Character count: {len(html_content)}")

        except Exception as e:
            print(f"[!] Scraper Error: {e}")
        finally:
            await browser.close()
            print("[FINISH] Session Complete.")

# --- FLASK WEB SERVER ---

@app.route('/')
def home():
    return "Dooka HTML Grabber is Active. Go to /view to see files.", 200

@app.route('/run')
def trigger():
    """Trigger the hunt in a separate thread."""
    t = threading.Thread(target=lambda: asyncio.run(start_hunt()))
    t.start()
    return "HTML Grab Started. Monitor logs for results.", 202

@app.route('/view')
def view():
    """Simple UI to see and click our saved files."""
    try:
        files = os.listdir(DATA_FOLDER)
        if not files:
            return "No files found. Hit /run first.", 200
        
        links = "".join([f'<li><a href="/download/{f}">{f}</a></li>' for f in files])
        return render_template_string(f"""
            <html>
                <body style="font-family:sans-serif; padding:20px;">
                    <h1>Dooka Scraped Data</h1>
                    <ul>{links}</ul>
                    <hr>
                    <a href="/run">Run New Hunt</a> | <a href="/">Home</a>
                </body>
            </html>
        """), 200
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/download/<path:filename>')
def download(filename):
    """Serve the actual HTML files."""
    return send_from_directory(DATA_FOLDER, filename)

if __name__ == "__main__":
    # Render binds the port to an environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

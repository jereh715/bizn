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

        categories = ["/mobile-phones", "/cars", "/electronics", "/home-appliances"]
        selected_cat = random.choice(categories)
        target_url = f"{BASE_URL}{selected_cat}"
        
        print(f"[*] Targeting: {target_url}")

        try:
            await page.goto(target_url, wait_until="load", timeout=60000)
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
    return "Dooka HTML Grabber is Active. Go to /view to see files.", 200

@app.route('/run')
def trigger():
    t = threading.Thread(target=lambda: asyncio.run(start_hunt()))
    t.start()
    return "HTML Grab Started. Check logs.", 202

# --- NEW VIEW & DOWNLOAD ROUTES ---

@app.route('/view')
def view():
    """Displays a simple list of clickable links to download the files."""
    try:
        files = os.listdir(DATA_FOLDER)
        if not files:
            return "No files found in storage yet. Run /run first.", 200
        
        # Create a simple HTML list of links
        links_html = "".join([f'<li><a href="/download/{f}">{f}</a></li>' for f in files])
        return render_template_string(f"""
            <h1>Scraped Data Files</h1>
            <ul>{links_html}</ul>
            <p><a href="/">Back Home</a></p>
        """), 200
    except Exception as e:
        return f"Error accessing storage: {str(e)}", 500

@app.route('/download/<path:filename>')
def download(filename):
    """Allows downloading the actual file."""
    return send_from_directory(DATA_FOLDER, filename, as_attachment=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

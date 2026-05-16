import asyncio
import os
import threading
import random
from flask import Flask, send_from_directory, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_URL = "https://my.hostafrica.com/cart.php"
DATA_FOLDER = "scraped_data"
os.makedirs(DATA_FOLDER, exist_ok=True)

async def start_hunt():
    """Launches Playwright to execute the Host Africa deep-link payload securely."""
    async with async_playwright() as p:
        print("[*] Launching Browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
        )
        
        page = await context.new_page()

        await page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://www.google.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site"
        })

        # Generate a test target domain name dynamically
        test_sld = f"testdomain{random.randint(1000, 9999)}"
        test_tld = ".co.ke"
        
        # Hardcoding your custom nameservers directly into the URL parameters
        custom_ns1 = "ns1.yourcustomhosting.com"
        custom_ns2 = "ns2.yourcustomhosting.com"

        # Constructing the exact WHMCS checkout injection URL
        target_url = (
            f"{BASE_URL}?a=add&domain=register"
            f"&sld={test_sld}"
            f"&tld={test_tld}"
            f"&ns1={custom_ns1}"
            f"&ns2={custom_ns2}"
        )
        
        print(f"[*] Targeting Host Africa Payload: {target_url}")

        try:
            # 1. Execute the redirect payload to spin up the remote session
            await page.goto(target_url, wait_until="load", timeout=60000)
            
            # 2. Allow their Single Page App framework time to generate 'cartState'
            print("[*] Page loaded. Waiting 8 seconds for LocalStorage state engine to sync...")
            await asyncio.sleep(8) 
            
            title = await page.title()
            print(f"[*] Current Page Title: {title}")
            
            if any(term in title for term in ["Cloudflare", "Verify", "Just a moment"]):
                print("[!] ALERT: Blocked by CDN gateway or verification layer.")
            else:
                print("[SUCCESS] Cart state injection initialized successfully.")

            # 3. Capture the post-execution HTML structure
            html_content = await page.content()
            filename = f"hostafrica_{test_sld}{test_tld}.html"
            filepath = os.path.join(DATA_FOLDER, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"[*] Post-execution HTML snapshot saved to {filepath}")
            print(f"[*] Character count: {len(html_content)}")

        except Exception as e:
            print(f"[!] Target Automation Error: {e}")
        finally:
            await browser.close()
            print("[FINISH] Session Complete.")

def run_async_loop(loop, coro):
    """Safely executes the async coroutine inside a designated background thread loop."""
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.close()

# --- FLASK WEB SERVER ---

@app.route('/')
def home():
    return "Host Africa Pipeline Active. Go to /view to see execution snapshots.", 200

@app.route('/run')
def trigger():
    """Trigger the execution loop cleanly using an isolated worker thread."""
    new_loop = asyncio.new_event_loop()
    t = threading.Thread(target=run_async_loop, args=(new_loop, start_hunt()))
    t.start()
    return "Host Africa Deep-Link Execution Started. Check console logs.", 202

@app.route('/view')
def view():
    """Simple UI to review the compiled output files."""
    try:
        files = os.listdir(DATA_FOLDER)
        if not files:
            return "No execution logs found. Hit /run first.", 200
        
        links = "".join([f'<li><a href="/download/{f}">{f}</a></li>' for f in files])
        return render_template_string(f"""
            <html>
                <body style="font-family:sans-serif; padding:20px;">
                    <h1>Host Africa Scraped States</h1>
                    <ul>{links}</ul>
                    <hr>
                    <a href="/run">Run New Session</a> | <a href="/">Home</a>
                </body>
            </html>
        """), 200
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/download/<path:filename>')
def download(filename):
    """Serve the generated HTML snapshots."""
    return send_from_directory(DATA_FOLDER, filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

import asyncio
import os
import threading
import random
import string
import functools
import json
import re
from flask import Flask, request, Response, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)

# --- CONFIGURATION ---
HOMEPAGE_URL = "https://www.hostafrica.co.ke/"

GLOBAL_P = None
GLOBAL_BROWSER = None
LOOP = None

def start_global_loop():
    global LOOP
    LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(LOOP)
    LOOP.run_until_complete(init_global_browser())
    LOOP.run_forever()

async def init_global_browser():
    global GLOBAL_P, GLOBAL_BROWSER
    print("[*] Initializing Global Browser Instance (Headless Mode: ON)...")
    GLOBAL_P = await async_playwright().start()
    
    # Optimized for headless hosting environments like Render
    GLOBAL_BROWSER = await GLOBAL_P.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1920,1080"
        ]
    )
    print("[SUCCESS] Global headless browser is ready for remote execution pipelines.")

def retry_async_action(retries=3, delay=5):
    """Decorator to retry asynchronous steps if selectors or actions fail."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(log_queue, *args, **kwargs):
            last_exception = None
            for attempt in range(1, retries + 1):
                try:
                    return await func(log_queue, *args, **kwargs)
                except Exception as e:
                    msg = f"[RETRY] Attempt {attempt}/{retries} failed for '{func.__name__}'. Error: {e}"
                    print(msg)
                    log_queue.put_nowait(msg)
                    last_exception = e
                    if attempt < retries:
                        await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

@retry_async_action(retries=3, delay=5)
async def run_homepage_pipeline(log_queue, page, domain_name):
    msg = f"[*] Navigating to Kenyan Homepage: {HOMEPAGE_URL}"
    log_queue.put_nowait(msg)
    await page.goto(HOMEPAGE_URL, wait_until="load", timeout=60000)
    
    input_selector = 'form.checkDomain #findtheperfectdomain'
    submit_button_selector = 'form.checkDomain #btn-domain_check'
    
    log_queue.put_nowait(f"[*] Typing target domain into form: {domain_name}")
    await page.wait_for_selector(input_selector, timeout=10000)
    await page.fill(input_selector, domain_name)
    
    log_queue.put_nowait("[*] Simulating form submission via availability check...")
    await page.click(submit_button_selector)
    
    log_queue.put_nowait("[*] Waiting for redirect pipeline to land on my.hostafrica.com...")
    await page.wait_for_load_state("load")
    log_queue.put_nowait("[SUCCESS] Redirect completed! Sitting on checkout page.")

@retry_async_action(retries=3, delay=5)
async def step_1_add_to_cart(log_queue, page, sld_prefix):
    button_selector = f'[id^="transfer-button-{sld_prefix}"]'
    log_queue.put_nowait(f"[*] [STEP 1/4] Targeting main row button for: {sld_prefix}")
    button_locator = page.locator(button_selector).first
    await button_locator.wait_for(state="visible", timeout=10000)
    await button_locator.scroll_into_view_if_needed()
    await button_locator.click()
    log_queue.put_nowait("[SUCCESS] Step 1 complete: Main row action clicked.")

@retry_async_action(retries=3, delay=5)
async def step_2_remove_addon(log_queue, page):
    log_queue.put_nowait("[*] [STEP 2/4] Attempting to remove 'Domain Warranty & Privacy' addon...")
    trash_btn_selector = 'i.v-icon--clickable.text-error[role="button"]'
    trash_locator = page.locator(trash_btn_selector).first
    
    if await trash_locator.count() > 0:
        await trash_locator.wait_for(state="visible", timeout=5000)
        await trash_locator.click()
        log_queue.put_nowait("[SUCCESS] Step 2 complete: Domain Privacy addon removed via trashcan icon.")
    else:
        log_queue.put_nowait("[*] Step 2 note: Trashcan icon not found. Already excluded.")

@retry_async_action(retries=3, delay=5)
async def step_3_click_pay_and_bypass_popup(log_queue, page):
    log_queue.put_nowait("[*] [STEP 3/4] Locating 'Pay Now' submission interface container...")
    pay_now_locator = page.locator('button .v-btn__content', has_text="Pay Now").first
    await pay_now_locator.wait_for(state="visible", timeout=10000)
    await pay_now_locator.scroll_into_view_if_needed()
    await pay_now_locator.click()
    log_queue.put_nowait("[SUCCESS] 'Pay Now' clicked. Awaiting domain privacy up-sell popup window...")
    
    await asyncio.sleep(5)
    
    no_thanks_locator = page.locator('span.v-btn__content', has_text="no, thank you").first
    await no_thanks_locator.wait_for(state="visible", timeout=5000)
    await no_thanks_locator.click()
    log_queue.put_nowait("[SUCCESS] Step 3 complete: Pop-up bypassed via 'no, thank you'. Proceeding to form...")

@retry_async_action(retries=3, delay=5)
async def step_4_inject_form_and_complete(log_queue, page, custom_email, custom_phone):
    log_queue.put_nowait("[*] [STEP 4/4] Activating state verification monitors for form modal...")
    form_selector = 'form.v-form'
    await page.wait_for_selector(form_selector, timeout=15000)
    
    first_name_input = page.locator('form.v-form input[autocomplete="new-firstname"]').first
    await first_name_input.wait_for(state="visible", timeout=15000)
    log_queue.put_nowait("[SUCCESS] Vuetify registration inputs locked. Starting injections...")
    
    log_queue.put_nowait(f"[*] Injecting identities -> First Name: ben, Last Name: dover, Email: {custom_email}")
    await first_name_input.fill("ben")
    await page.locator('form.v-form input[autocomplete="new-lastname"]').first.fill("dover")
    await page.locator('form.v-form input[autocomplete="email"]').first.fill(custom_email)
    
    log_queue.put_nowait(f"[*] Injecting telephone context: {custom_phone}")
    await page.locator('.v-phone-input__phone__input input[type="tel"]').first.fill(custom_phone)

    log_queue.put_nowait("[*] Injecting regional billing destination specifications...")
    await page.locator('form.v-form input[autocomplete="new-address1"]').first.fill("nairobi")
    await page.locator('form.v-form input[autocomplete="new-city"]').first.fill("nairobi")
    await page.locator('form.v-form input[autocomplete="new-state"]').first.fill("nairobi")
    await page.locator('form.v-form input[autocomplete="new-postcode"]').first.fill("00000")

    log_queue.put_nowait("[*] Locating and clicking the view/reveal password eye toggle icon...")
    eye_toggle_selector = 'i[aria-label="Password appended action"]'
    await page.wait_for_selector(eye_toggle_selector, timeout=10000)
    await page.click(eye_toggle_selector)
    await asyncio.sleep(0.5)
    
    log_queue.put_nowait("[*] Reading autofilled text payload straight from visible password element field...")
    recovered_password = await page.locator('form.v-form .passField input[type="text"]').first.input_value()
    log_queue.put_nowait(f"[SUCCESS] Safely Extracted Natively Autofilled Password: {recovered_password}")

    complete_btn = page.locator('form.v-form button .v-btn__content', has_text="Complete registration").first
    await complete_btn.scroll_into_view_if_needed()
    
    log_queue.put_nowait("[*] Dispatching system submit action click downstream...")
    await complete_btn.click()
    log_queue.put_nowait("[SUCCESS] Complete transaction form execution completed successfully!")
    
    return recovered_password

async def stream_integrated_workflow(log_queue, custom_sld, custom_email, custom_phone):
    """Runs the unified automated sequence and logs status steps in real-time to the queue channel."""
    global GLOBAL_BROWSER
    if not GLOBAL_BROWSER:
        log_queue.put_nowait("ERROR: Global browser instance is not initialized.")
        log_queue.put_nowait("DONE")
        return

    log_queue.put_nowait("[*] Spawning clean localized browser context...")
    context = await GLOBAL_BROWSER.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={'width': 1920, 'height': 1080}
    )
    
    page = await context.new_page()
    domain_name = f"{custom_sld}.co.ke"

    try:
        await run_homepage_pipeline(log_queue, page, domain_name)
        await step_1_add_to_cart(log_queue, page, custom_sld)
        await asyncio.sleep(1.5)
        
        await step_2_remove_addon(log_queue, page)
        await asyncio.sleep(1.5)
        
        await step_3_click_pay_and_bypass_popup(log_queue, page)
        await asyncio.sleep(1.5)
        
        password_captured = await step_4_inject_form_and_complete(log_queue, page, custom_email, custom_phone)
        
        log_queue.put_nowait("[*] Awaiting payment processing system confirmation redirect...")
        invoice_url = ""
        invoice_id = "UNKNOWN"
        for _ in range(30):
            await asyncio.sleep(1)
            current_url = page.url
            if "viewinvoice.php" in current_url:
                invoice_url = current_url
                log_queue.put_nowait(f"[SUCCESS] Checkout complete. Found Invoice Destination Link: {invoice_url}")
                
                id_match = re.search(r'id=(\d+)', current_url)
                if id_match:
                    invoice_id = id_match.group(1)
                    log_queue.put_nowait(f"[*] Parsed Invoice Core ID Reference: {invoice_id}")
                break
        
        await context.close()
        
        final_payload = {
            "status": "COMPLETE",
            "domain": domain_name,
            "email": custom_email,
            "password": password_captured,
            "invoice_url": invoice_url if invoice_url else "Timeout Redirect",
            "invoice_id": invoice_id
        }
        log_queue.put_nowait(f"FINAL_RESULT:{json.dumps(final_payload)}")
        log_queue.put_nowait("DONE")

    except Exception as workflow_error:
        await context.close()
        log_queue.put_nowait(f"[CRITICAL FAILURE] Integrated pipeline collapsed: {workflow_error}")
        log_queue.put_nowait("DONE")


# --- FLASK HTML INTERFACES ---

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>HostAfrica Order Provisioning Automation Engine</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; margin: 0; padding: 40px; color: #1e293b; }
        .container { max-width: 900px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
        h2 { margin-top: 0; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        label { display: block; font-weight: 600; font-size: 14px; margin-bottom: 6px; color: #475569; }
        input { width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        button { background: #2563eb; color: white; border: none; padding: 12px 24px; font-size: 15px; font-weight: 600; border-radius: 6px; cursor: pointer; transition: background 0.2s; width: 100%; }
        button:hover { background: #1d4ed8; }
        #terminal { background: #0f172a; color: #38bdf8; font-family: "Courier New", Courier, monospace; padding: 20px; border-radius: 8px; height: 260px; overflow-y: auto; margin-top: 25px; font-size: 13px; line-height: 1.5; box-shadow: inset 0 2px 4px 0 rgb(0 0 0 / 0.5); }
        #resultCard { display: none; background: #ecfdf5; border: 1px solid #a7f3d0; padding: 20px; border-radius: 8px; margin-top: 25px; color: #065f46; }
        .res-row { margin-bottom: 8px; font-size: 15px; }
        .res-row strong { color: #047857; width: 160px; display: inline-block; }
        code { background: #d1fae5; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 14px; font-weight: bold; color: #065f46; }
        a { color: #2563eb; font-weight: bold; text-decoration: none; }
        a:hover { text-decoration: underline; }
        
        .mpesa-container { background: #f0fdf4; border-left: 5px solid #22c55e; padding: 15px; border-radius: 4px; margin-top: 15px; font-family: sans-serif; color: #14532d; }
        .mpesa-title { font-weight: bold; font-size: 16px; margin-bottom: 10px; color: #166534; display: flex; align-items: center; }
        .mpesa-step { font-size: 14px; margin-bottom: 4px; padding-left: 5px; }
        .mpesa-highlight { background: #bbf7d0; color: #166534; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        <h2>HostAfrica Automation Workflow Dashboard</h2>
        <form id="automationForm">
            <div class="grid">
                <div>
                    <label>SLD Domain Name</label>
                    <input type="text" name="domain" id="domain" placeholder="e.g. kondiyi" required>
                </div>
                <div>
                    <label>Email Address</label>
                    <input type="email" name="email" id="email" placeholder="e.g. user@gmail.com" required>
                </div>
                <div>
                    <label>Phone Number</label>
                    <input type="text" name="phone" id="phone" value="+254712345678" required>
                </div>
            </div>
            <button type="submit" id="submitBtn">Launch Order Automation Pipeline</button>
        </form>

        <div id="resultCard">
            <h3 style="margin-top:0; border-bottom: 1px solid #a7f3d0; padding-bottom: 5px;">Execution Results Matrix</h3>
            <div class="res-row"><strong>Target Domain:</strong> <span id="resDomain"></span></div>
            <div class="res-row"><strong>Allocated Username:</strong> <span id="resEmail"></span></div>
            <div class="res-row"><strong>Captured Password:</strong> <code id="resPassword"></code></div>
            <div class="res-row"><strong>Final Invoice Link:</strong> <span id="resInvoice"></span></div>
            
            <div class="mpesa-container">
                <div class="mpesa-title">💸 Lipa na M-PESA Micro-Payment Gate Instructions</div>
                <div class="mpesa-step">1. Go to Safaricom Menu</div>
                <div class="mpesa-step">2. Select <b>M-PESA</b></div>
                <div class="mpesa-step">3. Select <b>Lipa na MPESA</b></div>
                <div class="mpesa-step">4. Select <b>Paybill</b></div>
                <div class="mpesa-step">5. Enter Business No: <span class="mpesa-highlight">890500</span></div>
                <div class="mpesa-step">6. Enter Account No: <span class="mpesa-highlight" id="mpesaAccount">Loading...</span></div>
                <div class="mpesa-step">7. Enter Amount (without commas): <span class="mpesa-highlight">462.84</span></div>
                <div class="mpesa-step">8. Enter your PIN and Confirm.</div>
            </div>
        </div>

        <div id="terminal">System Core Idle. Awaiting launch triggers...<br></div>
    </div>

    <script>
        document.getElementById('automationForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitBtn = document.getElementById('submitBtn');
            const term = document.getElementById('terminal');
            const resultCard = document.getElementById('resultCard');
            
            submitBtn.disabled = true;
            submitBtn.style.background = '#64748b';
            submitBtn.innerText = 'Automation Running...';
            resultCard.style.display = 'none';
            term.innerHTML = "<b>[SYSTEM START] Initializing Live Connection To Pipeline Monitor Stream...</b><br>";

            const domain = document.getElementById('domain').value;
            const email = document.getElementById('email').value;
            const phone = document.getElementById('phone').value;

            const eventSource = new EventSource(`/stream?domain=${encodeURIComponent(domain)}&email=${encodeURIComponent(email)}&phone=${encodeURIComponent(phone)}`);

            eventSource.onmessage = function(event) {
                const data = event.data;

                if (data === "DONE") {
                    eventSource.close();
                    submitBtn.disabled = false;
                    submitBtn.style.background = '#2563eb';
                    submitBtn.innerText = 'Launch Order Automation Pipeline';
                    term.innerHTML += "<b>[SYSTEM END] Connection completed cleanly. Terminal Closed.</b><br>";
                    term.scrollTop = term.scrollHeight;
                } 
                else if (data.startsWith("FINAL_RESULT:")) {
                    const payload = JSON.parse(data.replace("FINAL_RESULT:", ""));
                    document.getElementById('resDomain').innerText = payload.domain;
                    document.getElementById('resEmail').innerText = payload.email;
                    document.getElementById('resPassword').innerText = payload.password;
                    document.getElementById('mpesaAccount').innerText = payload.invoice_id;
                    
                    if (payload.invoice_url.startsWith("http")) {
                        document.getElementById('resInvoice').innerHTML = `<a href="${payload.invoice_url}" target="_blank">${payload.invoice_url}</a>`;
                    } else {
                        document.getElementById('resInvoice').innerText = payload.invoice_url;
                    }
                    resultCard.style.display = 'block';
                } 
                else {
                    term.innerHTML += data + "<br>";
                    term.scrollTop = term.scrollHeight;
                }
            };

            eventSource.onerror = function() {
                term.innerHTML += "<span style='color:#ef4444;'>[ERROR] EventSource failed or lost connection channel.</span><br>";
                eventSource.close();
                submitBtn.disabled = false;
                submitBtn.style.background = '#2563eb';
                submitBtn.innerText = 'Launch Order Automation Pipeline';
            };
        });
    </script>
</body>
</html>
"""

@app.route('/')
def load_dashboard_ui():
    return render_template_string(DASHBOARD_HTML)

@app.route('/stream')
def logs_sse_stream_endpoint():
    global LOOP
    if not LOOP or not LOOP.is_running():
        return "Background environment loop offline.", 500

    custom_domain = request.args.get('domain', '').strip()
    custom_email = request.args.get('email', '').strip()
    custom_phone = request.args.get('phone', '+254124567890').strip()

    if not custom_domain:
        custom_domain = f"testdomain{random.randint(1000, 9999)}"
    if not custom_email:
        custom_email = f"dummy_{random.randint(100,999)}@gmail.com"

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        stream_integrated_workflow(log_queue, custom_domain, custom_email, custom_phone),
        LOOP
    )

    def event_stream_generator():
        while True:
            future = asyncio.run_coroutine_threadsafe(log_queue.get(), LOOP)
            log_line = future.result()
            
            yield f"data: {log_line}\n\n"
            if log_line == "DONE":
                break

    return Response(event_stream_generator(), mimetype='text/event-stream')


if __name__ == "__main__":
    t = threading.Thread(target=start_global_loop, daemon=True)
    t.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

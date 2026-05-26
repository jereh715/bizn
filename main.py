import asyncio
import os
import threading
import random
import json
import re
import functools
import time
from flask import Flask, request, jsonify
from flask_sock import Sock
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

app = Flask(__name__)
sock = Sock(app)

# --- CONFIGURATION ---
HOMEPAGE_URL = "https://www.hostafrica.ke/"

GLOBAL_P = None
GLOBAL_BROWSER = None
LOOP = None


# --- RUNTIME LOOPS MANAGEMENT ---

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

def ensure_background_loop_is_alive():
    """Failsafe manager to boot the background thread if Gunicorn drops it inside Docker."""
    global LOOP
    if LOOP is None or not LOOP.is_running():
        print("[!] Background event loop detected as OFFLINE. Spawning new initialization thread...")
        t = threading.Thread(target=start_global_loop, daemon=True)
        t.start()
        
        for _ in range(3):
            if LOOP and LOOP.is_running():
                print("[SUCCESS] Background event loop successfully recovered and is now ONLINE.")
                break
            time.sleep(1)

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


# --- REGISTRATION / PURCHASING PIPELINE STEPS ---

@retry_async_action(retries=3, delay=5)
async def run_homepage_pipeline(log_queue, page, domain_name):
    msg = f"[*] Navigating to Kenyan Homepage: {HOMEPAGE_URL}"
    log_queue.put_nowait(msg)
    await page.goto(HOMEPAGE_URL, wait_until="load", timeout=60000)
    
    input_selector = '#findtheperfectdomain'
    submit_button_selector = '#btn-domain_check'
    
    log_queue.put_nowait(f"[*] Typing target domain into form: {domain_name}")
    await page.wait_for_selector(input_selector, timeout=15000)
    await page.fill(input_selector, domain_name)
    
    log_queue.put_nowait("[*] Simulating form submission via availability check...")
    await page.click(submit_button_selector)
    
    log_queue.put_nowait("[*] Waiting for redirect pipeline to land on my.hostafrica.com...")
    await page.wait_for_load_state("domcontentloaded")
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
async def step_4_inject_form_and_complete(log_queue, page, first_name, last_name, custom_email, custom_phone, custom_password):
    log_queue.put_nowait("[*] [STEP 4/4] Activating state verification monitors for form modal...")
    form_selector = 'form.v-form'
    await page.wait_for_selector(form_selector, timeout=15000)
    
    first_name_input = page.locator('form.v-form input[autocomplete="new-firstname"]').first
    await first_name_input.wait_for(state="visible", timeout=15000)
    log_queue.put_nowait("[SUCCESS] Vuetify registration inputs locked. Starting injections...")
    
    log_queue.put_nowait(f"[*] Injecting identities -> First Name: {first_name}, Last Name: {last_name}, Email: {custom_email}")
    await first_name_input.fill(first_name)
    await page.locator('form.v-form input[autocomplete="new-lastname"]').first.fill(last_name)
    await page.locator('form.v-form input[autocomplete="email"]').first.fill(custom_email)
    
    log_queue.put_nowait(f"[*] Injecting telephone context: {custom_phone}")
    await page.locator('.v-phone-input__phone__input input[type="tel"]').first.fill(custom_phone)

    log_queue.put_nowait("[*] Injecting regional billing destination specifications...")
    await page.locator('form.v-form input[autocomplete="new-address1"]').first.fill("nairobi")
    await page.locator('form.v-form input[autocomplete="new-city"]').first.fill("nairobi")
    await page.locator('form.v-form input[autocomplete="new-state"]').first.fill("nairobi")
    await page.locator('form.v-form input[autocomplete="new-postcode"]').first.fill("00000")

    log_queue.put_nowait("[*] Intercepting registration password element arrays...")
    password_fields = page.locator('form.v-form .passField input')
    
    await password_fields.nth(0).wait_for(state="visible", timeout=15000)
    
    for index in range(2):
        field_label = "Primary" if index == 0 else "Repeat/Confirmation"
        log_queue.put_nowait(f"[*] Processing password input sequencing for -> [{field_label} Field] at index {index}")
        
        target_input = password_fields.nth(index)
        await target_input.scroll_into_view_if_needed()
        
        await target_input.focus()
        await target_input.click()
        
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)
        
        await target_input.type(custom_password, delay=100)
        await asyncio.sleep(0.5)
        
    log_queue.put_nowait("[SUCCESS] Both password entries executed and synced successfully.")
    
    eye_toggle_selector = 'i[aria-label="Password appended action"]'
    await page.wait_for_selector(eye_toggle_selector, timeout=10000)
    await page.click(eye_toggle_selector)
    await asyncio.sleep(0.5)
    
    recovered_password = await password_fields.nth(0).input_value()
    log_queue.put_nowait(f"[SUCCESS] Verified Active Form Registration Password: {recovered_password}")

    complete_btn = page.locator('form.v-form button .v-btn__content', has_text="Complete registration").first
    await complete_btn.scroll_into_view_if_needed()
    
    log_queue.put_nowait("[*] Dispatching system submit action click downstream...")
    await complete_btn.click()
    log_queue.put_nowait("[SUCCESS] Complete transaction form execution completed successfully!")
    
    return recovered_password

@retry_async_action(retries=3, delay=5)
async def trigger_mpesa_express_stk_push(log_queue, page):
    log_queue.put_nowait("[*] Locating Invoice Portal Pay Now anchor action selector...")
    
    invoice_pay_now = page.locator('a[data-target="#modalLoginForm"]').first
    await invoice_pay_now.wait_for(state="visible", timeout=15000)
    await invoice_pay_now.scroll_into_view_if_needed()
    
    log_queue.put_nowait("[*] Clicking Invoice Pay Now button to launch MPESA overlay interface...")
    await invoice_pay_now.click()
    
    send_request_btn = page.locator('button#send-request').first
    await send_request_btn.wait_for(state="visible", timeout=15000)
    
    log_queue.put_nowait("[*] STK Overlay loaded. Dispatched click event onto 'Send Request to Phone' trigger action...")
    await send_request_btn.click()
    log_queue.put_nowait("[SUCCESS] M-PESA Express STK Push handshake sent successfully out to handset device!")


async def stream_integrated_workflow(log_queue, custom_sld, first_name, last_name, custom_email, custom_phone, custom_password, payment_method):
    global GLOBAL_BROWSER
    if not GLOBAL_BROWSER:
        log_queue.put_nowait("ERROR: Global browser instance is not initialized.")
        log_queue.put_nowait("DONE")
        return

    log_queue.put_nowait("[*] Spawning clean localized browser context...")
    context = await GLOBAL_BROWSER.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36",
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
        
        password_captured = await step_4_inject_form_and_complete(log_queue, page, first_name, last_name, custom_email, custom_phone, custom_password)
        
        log_queue.put_nowait("[*] Awaiting payment processing system confirmation redirect...")
        invoice_url = ""
        invoice_id = "UNKNOWN"
        is_invoice_found = False
        
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
                
                is_invoice_found = True
                break
        
        if is_invoice_found:
            if payment_method == "stk":
                log_queue.put_nowait("[*] User configuration targeted: M-PESA Express (STK Prompt Mode)")
                await trigger_mpesa_express_stk_push(log_queue, page)
                
                log_queue.put_nowait("[*] Commencing 45-second countdown runtime loop window for manual M-PESA handset confirmation...")
                for seconds_left in range(45, 0, -5):
                    log_queue.put_nowait(f"[WAITING] Holding automation link open. Channel shuts down in {seconds_left} seconds...")
                    await asyncio.sleep(5)
            else:
                log_queue.put_nowait("[SUCCESS] User configuration targeted: Manual Paybill Presentation. Skipping automated STK phone injection loops.")
        else:
            log_queue.put_nowait("[WARN] Failed to intercept structural invoice panel context within time boundaries.")
        
        final_payload = {
            "status": "COMPLETE",
            "domain": domain_name,
            "email": custom_email,
            "password": password_captured,
            "invoice_url": invoice_url if invoice_url else "Timeout Redirect",
            "invoice_id": invoice_id,
            "payment_method": payment_method,
            "timestamp": int(time.time())
        }
        log_queue.put_nowait(f"FINAL_RESULT:{json.dumps(final_payload)}")

    except Exception as workflow_error:
        log_queue.put_nowait(f"[CRITICAL FAILURE] Integrated pipeline collapsed: {workflow_error}")
    
    finally:
        await context.close()
        log_queue.put_nowait("DONE")


# --- ASYNCHRONOUS DIRECT CARTS DOMAIN CHECKER WORKFLOW ---

async def stream_domain_check_workflow(log_queue, custom_sld):
    global GLOBAL_BROWSER
    if not GLOBAL_BROWSER:
        log_queue.put_nowait("ERROR: Global browser instance is not initialized.")
        log_queue.put_nowait("DONE")
        return

    domain_clean = re.sub(r'\.[a-zA-Z.]+$', '', custom_sld)
    full_target_domain = f"{domain_clean}.co.ke"
    direct_cart_url = f"https://my.hostafrica.com/cart.php?a=add&domain=register&sld={domain_clean}&tld=.co.ke&currency=3"

    log_queue.put_nowait(f"[*] Initializing isolation context for scan task: {full_target_domain}")
    context = await GLOBAL_BROWSER.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={'width': 1920, 'height': 1080}
    )
    page = await context.new_page()

    try:
        log_queue.put_nowait(f"[*] Injected deep link payload navigation targeting: {direct_cart_url}")
        await page.goto(direct_cart_url, wait_until="load", timeout=30000)
        log_queue.put_nowait("[*] Awaiting layout data parsing generation...")
        
        try:
            await page.wait_for_selector("div.v-row--no-gutters", timeout=12000)
        except Exception:
            log_queue.put_nowait("[WARN] Matrix elements delayed. Running direct context parse step.")
        
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        results_matrix = []
        is_target_handled = False

        internal_msg = soup.find("div", class_="v-messages__message")
        if internal_msg and "already registered with us" in internal_msg.text.lower():
            log_queue.put_nowait(f"[!] Alert: Target registered internally within HostAfrica node maps.")
            results_matrix.append({
                "domain": full_target_domain,
                "status": "NOT_AVAILABLE_HOSTAFRICA",
                "price": "N/A"
            })
            is_target_handled = True

        domain_rows = soup.find_all("div", class_="v-row--no-gutters")
        for row in domain_rows:
            domain_name_tag = row.find(class_="domainEntryPanel--domainName")
            if not domain_name_tag:
                continue
                
            found_domain = domain_name_tag.text.strip()
            price_span = row.find("span", class_="text-nowrap")
            if price_span and price_span.find("strong"):
                price = price_span.find("strong").text.strip()
            else:
                price = "Pricing Undefined/NA"
                
            taken_label = row.find("span", class_="domainEntryPanel--label--taken")
            if taken_label and "taken" in taken_label.text.lower():
                status = "TAKEN"
            else:
                status = "AVAILABLE"

            if found_domain.lower() == full_target_domain.lower() and is_target_handled:
                continue

            results_matrix.append({
                "domain": found_domain,
                "status": status,
                "price": price
            })

        if not results_matrix:
            log_queue.put_nowait("[WARN] No operational records parsed from HostAfrica structural matrix layout.")

        final_payload = {
            "status": "SUCCESS",
            "query_domain": full_target_domain,
            "results": results_matrix
        }
        log_queue.put_nowait(f"FINAL_RESULT:{json.dumps(final_payload)}")

    except Exception as check_error:
        log_queue.put_nowait(f"[CRITICAL FAILURE] Verification sequence failed: {check_error}")
    finally:
        await context.close()
        log_queue.put_nowait("DONE")


# --- HTTP ROUTES & WEBSOCKET ENDPOINTS ---

@app.route('/')
def index():
    ensure_background_loop_is_alive()
    return jsonify({"status": "ONLINE", "message": "HostAfrica Automation Engine Running"}), 200

@app.route('/healthz')
def keep_alive_health_check():
    ensure_background_loop_is_alive()
    return jsonify({"status": "HEALTHY"}), 200


@sock.route('/ws/stream')
def logs_websocket_stream_endpoint(ws):
    ensure_background_loop_is_alive()
    global LOOP
    if not LOOP or not LOOP.is_running():
        ws.send("ERROR: Background environment loop offline.")
        return

    custom_domain = request.args.get('domain', '').strip()
    first_name = request.args.get('first_name', 'ben').strip()
    last_name = request.args.get('last_name', 'dover').strip()
    custom_email = request.args.get('email', '').strip()
    custom_password = request.args.get('password', '').strip()
    custom_phone = request.args.get('phone', '+254712345678').strip()
    payment_method = request.args.get('payment_method', 'stk').strip()

    if not custom_domain:
        custom_domain = f"testdomain{random.randint(1000, 9999)}"
    if not custom_email:
        custom_email = f"dummy_{random.randint(100,999)}@gmail.com"
    if not custom_password:
        custom_password = f"Pass_{random.randint(10000,99999)}!"

    if "@gmail.com" in custom_email.lower() and "+" not in custom_email:
        parts = custom_email.split('@')
        username = parts[0]
        domain_name = parts[1]
        
        epoch_secs = int(time.time())
        unique_token = epoch_secs % 1000000
        unique_token_str = f"{unique_token:06d}"
        
        custom_email = f"{username}+{unique_token_str}@{domain_name}"

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        stream_integrated_workflow(log_queue, custom_domain, first_name, last_name, custom_email, custom_phone, custom_password, payment_method),
        LOOP
    )

    while True:
        future = asyncio.run_coroutine_threadsafe(log_queue.get(), LOOP)
        log_line = future.result()
        
        try:
            ws.send(log_line)
        except Exception:
            print("[*] Connection closed downstream by customer interface environment.")
            break
            
        if log_line == "DONE":
            break


@sock.route('/ws/check')
def logs_websocket_check_endpoint(ws):
    ensure_background_loop_is_alive()
    global LOOP
    if not LOOP or not LOOP.is_running():
        ws.send("ERROR: Background environment loop offline.")
        return

    custom_domain = request.args.get('domain', '').strip()
    if not custom_domain:
        ws.send("ERROR: Missing required 'domain' tracking parameter query string.")
        ws.send("DONE")
        return

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        stream_domain_check_workflow(log_queue, custom_domain),
        LOOP
    )

    while True:
        future = asyncio.run_coroutine_threadsafe(log_queue.get(), LOOP)
        log_line = future.result()
        
        try:
            ws.send(log_line)
        except Exception:
            print("[*] Scan tracking connection disconnected by programmatic consumer interface client.")
            break
            
        if log_line == "DONE":
            break


if __name__ == "__main__":
    ensure_background_loop_is_alive()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Launching local Flask Server Engine on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

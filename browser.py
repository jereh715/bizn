import asyncio
import os
import threading
import random
import json
import re
import functools
import time
import urllib.request
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# --- MODULE STATE ---
GLOBAL_P = None
GLOBAL_BROWSER = None
LOOP = None
HOMEPAGE_URL = "https://www.hostafrica.ke/"

# --- HARDCODED DOMAIN PRICING MATRIX ---
LOCAL_FALLBACK = {
    ".co.ke": {"category": "Africa", "registration_price": "KSh463", "renewal_price": "KSh2,350"},
    ".ke": {"category": "Africa", "registration_price": "KSh3,000", "renewal_price": "KSh3,000"},
    ".ac.ke": {"category": "Africa", "registration_price": "KSh1,450", "renewal_price": "KSh2,350"},
    ".sc.ke": {"category": "Africa", "registration_price": "KSh1,450", "renewal_price": "KSh2,350"},
    ".me.ke": {"category": "Africa", "registration_price": "KSh1,450", "renewal_price": "KSh2,350"},
    ".info.ke": {"category": "Africa", "registration_price": "KSh1,450", "renewal_price": "KSh2,350"},
    ".com": {"category": "Technology", "registration_price": "KSh2,120", "renewal_price": "KSh2,990"},
    ".org": {"category": "Technology", "registration_price": "KSh2,500", "renewal_price": "KSh2,990"},
    ".net": {"category": "Technology", "registration_price": "KSh2,600", "renewal_price": "KSh2,990"},
    ".africa": {"category": "Africa", "registration_price": "KSh1,059", "renewal_price": "KSh2,299"}
}


def get_cached_prices_for_domain(domain_name):
    """
    Parses domain names and matches them against the local hardcoded TLD matrix.
    Sorts keys by length descending to avoid greedy partial matches (e.g. matching .co.ke before .ke).
    """
    try:
        domain_clean = domain_name.strip().lower()
        
        # Sort extensions by string length descending (.co.ke matches before checking .ke)
        sorted_fallback = sorted(LOCAL_FALLBACK.items(), key=lambda x: len(x[0]), reverse=True)
        
        for tld, metrics in sorted_fallback:
            if domain_clean.endswith(tld):
                return metrics
    except Exception as e:
        print(f"[BROWSER PRICING ERROR] Failed executing local pricing lookup: {e}")
        
    return {"category": "Unknown", "registration_price": "N/A", "renewal_price": "N/A"}


# --- SUPABASE REST STORAGE ADAPTER (TWO-PHASE SUPPORT) ---

def sync_domain_record_to_web(payload, record_id=None):
    """
    Handles both initial insertion (POST) and subsequent updates (PATCH).
    If record_id is provided, it targets that specific row via its ID.
    """
    base_url = "https://zeccnkbazpqjztjrifsx.supabase.co/rest/v1/domain_records"
    service_role_key = "sb_secret_xtVXHEqfMyEkeuSoob8sKw_awiu8BEH"
    
    if record_id:
        # Phase 2: Updating the existing pending record
        target_url = f"{base_url}?id=eq.{record_id}"
        method = 'PATCH'
        print(f"[*] Updating existing record ID {record_id} to SUCCESS status...")
    else:
        # Phase 1: Creating a brand new pending record
        target_url = base_url
        method = 'POST'
        print(f"[*] Creating immediate PENDING record for: {payload.get('domain')}")
        
    try:
        json_bytes = json.dumps(payload).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'apikey': service_role_key,
            'Authorization': f'Bearer {service_role_key}',
            'User-Agent': 'Render-Automation-Engine'
        }
        
        # Request Supabase to return the inserted row data back to get its ID
        if method == 'POST':
            headers['Prefer'] = 'return=representation'
        else:
            headers['Prefer'] = 'return=minimal'
            
        req = urllib.request.Request(
            target_url,
            data=json_bytes,
            headers=headers,
            method=method
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            status_code = response.getcode()
            if status_code in (200, 201):
                if method == 'POST':
                    res_data = json.loads(response.read().decode('utf-8'))
                    if isinstance(res_data, list) and len(res_data) > 0:
                        print("[SUCCESS] Initial PENDING state saved to Supabase.")
                        return res_data[0].get('id')  # Returns the DB row ID for subsequent patch
                print("[SUCCESS] Supabase Database Synchronization Complete.")
                return True
            else:
                print(f"[STORAGE ERROR] Supabase backend rejected payload with status code: {status_code}")
                return None if method == 'POST' else False
                
    except Exception as http_err:
        print(f"[STORAGE PIPELINE FAILURE] Supabase REST route collapsed: {http_err}")
        return None if method == 'POST' else False


# --- RUNTIME LOOPS MANAGEMENT (GUNICORN / MULTI-THREAD SAFE) ---

def start_global_loop():
    global LOOP
    try:
        LOOP = asyncio.get_running_loop()
        print("[*] Hooked into an existing running event loop context.")
    except RuntimeError:
        if LOOP is None:
            try:
                LOOP = asyncio.get_event_loop()
            except RuntimeError:
                LOOP = asyncio.new_event_loop()
                asyncio.set_event_loop(LOOP)
    
    if not LOOP.is_running():
        LOOP.run_until_complete(init_global_browser())
        try:
            LOOP.run_forever()
        except RuntimeError as e:
            if "already running" in str(e):
                print("[*] Defensive Guard: Event loop is already running safely downstream.")
            else:
                raise e
    else:
        print("[*] Event loop active. Scheduling global browser initialization...")
        asyncio.run_coroutine_threadsafe(init_global_browser(), LOOP)

async def init_global_browser():
    global GLOBAL_P, GLOBAL_BROWSER
    if GLOBAL_BROWSER:
        print("[*] Global browser instance already alive. Skipping redundant init pass.")
        return

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
    global LOOP
    if LOOP is None or not LOOP.is_running():
        print("[!] Background event loop detected as OFFLINE. Spawning safe initialization thread...")
        t = threading.Thread(target=start_global_loop, daemon=True)
        t.start()
        
        for _ in range(3):
            if LOOP and LOOP.is_running():
                print("[SUCCESS] Background event loop successfully recovered and is now ONLINE.")
                break
            time.sleep(1)
    else:
        if not GLOBAL_BROWSER:
            print("[!] Loop is online but browser instance is missing. Hot-patching initialization...")
            asyncio.run_coroutine_threadsafe(init_global_browser(), LOOP)

def get_loop():
    global LOOP
    if LOOP is None:
        ensure_background_loop_is_alive()
    return LOOP

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
    
    log_queue.put_nowait("[*] Waiting for redirect pipeline to land and network to settle on my.hostafrica.com...")
    # Swapped to networkidle to guarantee Vue/Vuetify async chunk assets have hydrated completely
    await page.wait_for_load_state("networkidle", timeout=30000)
    log_queue.put_nowait("[SUCCESS] Redirect completed! Sitting on checkout page.")

@retry_async_action(retries=3, delay=5)
async def step_1_add_to_cart(log_queue, page, domain_name):
    # FIX: HostAfrica normalizes domain dashes/hyphens to underscores inside the element IDs.
    prefix = domain_name.split('.')[0].replace('-', '_')
    button_selector = f'[id^="transfer-button-{prefix}"]'
    log_queue.put_nowait(f"[*] [STEP 1/4] Targeting main row button for prefix: {prefix} (Domain: {domain_name})")
    
    # Extra check: Ensure network is quiet so rows are fully compiled
    await page.wait_for_load_state("networkidle", timeout=15000)
    
    button_locator = page.locator(button_selector).first
    # Two-stage check: Wait until attached to DOM tree, then wait until visible to the view matrix
    await button_locator.wait_for(state="attached", timeout=10000)
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
    
    # FIX: Targeted the interactive button node directly, checking for attached + visible states
    pay_now_locator = page.locator('button:has-text("Pay Now")').first
    await pay_now_locator.wait_for(state="attached", timeout=15000)
    await pay_now_locator.wait_for(state="visible", timeout=15000)
    await pay_now_locator.scroll_into_view_if_needed()
    
    # Force click bypasses hidden clipping issues caused by temporary Vuetify overlay loaders
    await pay_now_locator.click(force=True)
    log_queue.put_nowait("[SUCCESS] 'Pay Now' clicked. Awaiting domain privacy up-sell popup window...")
    
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(4)
    
    # FIX: Native button text match instead of searching inside internal spans
    no_thanks_locator = page.locator('button:has-text("no, thank you")').first
    await no_thanks_locator.wait_for(state="visible", timeout=10000)
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
    complete_btn.scroll_into_view_if_needed()
    
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


# --- INTEGRATED STREAM COORDINATORS ---

async def stream_integrated_workflow(log_queue, auth_username, custom_domain, first_name, last_name, custom_email, custom_phone, custom_password, payment_method):
    global GLOBAL_BROWSER
    if not GLOBAL_BROWSER:
        log_queue.put_nowait("ERROR: Global browser instance is not initialized.")
        log_queue.put_nowait("DONE")
        return

    domain_name = custom_domain.strip().lower()
    loop = asyncio.get_event_loop()

    price_metrics = get_cached_prices_for_domain(domain_name)

    # =========================================================================
    # PHASE 1: IMMEDIATE INITIAL SAVE (Fills baseline details, status=PENDING)
    # =========================================================================
    log_queue.put_nowait("[*] Registering initial intent handshake with database...")
    initial_payload = {
        "username": auth_username,
        "domain": domain_name,
        "email": custom_email,
        "status": "PENDING",
        "timestamp": int(time.time()),
        "invoice_url": "Processing automation pipelines...",
        "invoice_id": "PENDING",
        "payment_method": payment_method,
        "category": price_metrics["category"],
        "registration_price": price_metrics["registration_price"],
        "renewal_price": price_metrics["renewal_price"]
    }
    
    db_record_id = await loop.run_in_executor(None, sync_domain_record_to_web, initial_payload)
    if db_record_id:
        log_queue.put_nowait(f"[SUCCESS] Tracking record live. Record ID Reference: {db_record_id}")
    else:
        log_queue.put_nowait("[WARN] Failed to establish early tracking hook. Continuing execution...")

    log_queue.put_nowait("[*] Spawning clean localized browser context...")
    context = await GLOBAL_BROWSER.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={'width': 1920, 'height': 1080}
    )
    
    page = await context.new_page()

    try:
        await run_homepage_pipeline(log_queue, page, domain_name)
        await step_1_add_to_cart(log_queue, page, domain_name)
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
        
        # =========================================================================
        # PHASE 2: FINAL DATA UPDATE (Patches missing details, changes status to SUCCESS)
        # =========================================================================
        final_payload = {
            "username": auth_username,
            "domain": domain_name,
            "email": custom_email,
            "password": password_captured if password_captured else custom_password,
            "invoice_url": invoice_url if invoice_url else "Timeout Redirect",
            "invoice_id": invoice_id,
            "payment_method": payment_method,
            "status": "SUCCESS",
            "timestamp": int(time.time()),
            "category": price_metrics["category"],
            "registration_price": price_metrics["registration_price"],
            "renewal_price": price_metrics["renewal_price"]
        }
        log_queue.put_nowait(f"FINAL_RESULT:{json.dumps(final_payload)}")

        if db_record_id:
            log_queue.put_nowait("[*] Storage Pipeline: Finalizing record status on remote Supabase structures...")
            sync_success = await loop.run_in_executor(None, sync_domain_record_to_web, final_payload, db_record_id)
            
            if sync_success:
                log_queue.put_nowait("[SUCCESS] Registration state successfully marked as complete on database.")
            else:
                log_queue.put_nowait("[WARN] Local execution finished, but Supabase final patch update route failed.")
        else:
            log_queue.put_nowait("[*] Storage Pipeline Fallback: Performing standard direct row creation hook...")
            await loop.run_in_executor(None, sync_domain_record_to_web, final_payload)

    except Exception as workflow_error:
        log_queue.put_nowait(f"[CRITICAL FAILURE] Integrated pipeline collapsed: {workflow_error}")
        if db_record_id:
            try:
                failure_payload = {"status": "FAILED", "invoice_url": f"Automation Failed: {workflow_error}"}
                await loop.run_in_executor(None, sync_domain_record_to_web, failure_payload, db_record_id)
            except Exception:
                pass
    finally:
        await context.close()
        log_queue.put_nowait("DONE")


async def stream_domain_check_workflow(log_queue, custom_domain):
    global GLOBAL_BROWSER
    if not GLOBAL_BROWSER:
        log_queue.put_nowait("ERROR: Global browser instance is not initialized.")
        log_queue.put_nowait("DONE")
        return

    full_target_domain = custom_domain.strip().lower()
    
    domain_match = re.match(r'^([^.]+)(?:\.(co\.ke|ke|com|net|org|xyz|biz))$', full_target_domain)
    if domain_match:
        sld_param = domain_match.group(1)
        tld_param = f".{domain_match.group(2)}"
    else:
        sld_param = full_target_domain.split('.')[0]
        tld_param = "." + ".".join(full_target_domain.split('.')[1:])

    direct_cart_url = f"https://my.hostafrica.com/cart.php?a=add&domain=register&sld={sld_param}&tld={tld_param}&currency=3"

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

        live_prices = get_cached_prices_for_domain(full_target_domain)

        internal_msg = soup.find("div", class_="v-messages__message")
        if internal_msg and "already registered with us" in internal_msg.text.lower():
            log_queue.put_nowait(f"[!] Alert: Target registered internally within HostAfrica node maps.")
            results_matrix.append({
                "domain": full_target_domain,
                "status": "NOT_AVAILABLE_HOSTAFRICA",
                "price": live_prices["registration_price"],
                "renewal_price": live_prices["renewal_price"],
                "category": live_prices["category"]
            })
            is_target_handled = True

        domain_rows = soup.find_all("div", class_="v-row--no-gutters")
        for row in domain_rows:
            domain_name_tag = row.find(class_="domainEntryPanel--domainName")
            if not domain_name_tag:
                continue
                
            found_domain = domain_name_tag.text.strip().lower()
            
            row_prices = get_cached_prices_for_domain(found_domain)
            
            price_span = row.find("span", class_="text-nowrap")
            if price_span and price_span.find("strong"):
                price = price_span.find("strong").text.strip()
            else:
                price = row_prices["registration_price"]
                
            taken_label = row.find("span", class_="domainEntryPanel--label--taken")
            if taken_label and "taken" in taken_label.text.lower():
                status = "TAKEN"
            else:
                status = "AVAILABLE"

            if found_domain == full_target_domain and is_target_handled:
                continue

            results_matrix.append({
                "domain": found_domain,
                "status": status,
                "price": price,
                "renewal_price": row_prices["renewal_price"],
                "category": row_prices["category"]
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

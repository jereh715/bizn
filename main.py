import os
import random
import time
import asyncio
import uuid
import string
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from threading import Lock
from flask import Flask, request, jsonify
from flask_cors import CORS  # Handles cross-origin resource sharing

# Import the third-party WHOIS library
import whois

# Import your monolithic background driver
import browser

app = Flask(__name__)

# --- ENABLE CORS ENGINE CORE ---
CORS(app, resources={r"/api/*": {"origins": "*"}}, allow_headers=["Content-Type", "X-API-Key"])

# Global tracking structures with explicit Thread Locking
ACTIVE_TASKS = {}
tasks_lock = Lock()

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

# Supabase Configurations for API Key checks
SUPABASE_URL = "https://zeccnkbazpqjztjrifsx.supabase.co"
SERVICE_ROLE_KEY = "sb_secret_xtVXHEqfMyEkeuSoob8sKw_awiu8BEH"


def match_pricing_for_domain(domain_name):
    """
    Helper function to parse domain names and match them with our local hardcoded TLD footprints.
    Sorts keys by length descending to avoid greedy partial matches (e.g. matching .co.ke before .ke).
    """
    domain_clean = domain_name.strip().lower()
    
    # Sort extensions by string length descending (.co.ke matches before checking .ke)
    sorted_fallback = sorted(LOCAL_FALLBACK.items(), key=lambda x: len(x[0]), reverse=True)
    
    for tld, metrics in sorted_fallback:
        if domain_clean.endswith(tld):
            return metrics
            
    return {"category": "Unknown", "registration_price": "N/A", "renewal_price": "N/A"}


def verify_api_key_in_supabase(api_key, username):
    """
    Queries the api_keys table directly via the REST interface 
    to see if the provided key exists, belongs to the given username, and is valid.
    """
    if not api_key or not username:
        return False
        
    target_url = f"{SUPABASE_URL}/rest/v1/api_keys?api_key=eq.{api_key}&username=eq.{urllib.parse.quote(username)}&status=eq.paid&select=*"
    
    try:
        req = urllib.request.Request(
            target_url,
            headers={
                'apikey': SERVICE_ROLE_KEY,
                'Authorization': f'Bearer {SERVICE_ROLE_KEY}'
            },
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return len(data) > 0
    except Exception as e:
        print(f"[AUTH ERROR] Failed to reach Supabase for key validation: {e}")
        return False


def save_api_key_to_supabase(username, api_key, status):
    """
    Boxes and saves a newly generated API key structural footprint into Supabase.
    """
    target_url = f"{SUPABASE_URL}/rest/v1/api_keys"
    payload = {
        "username": username,
        "api_key": api_key,
        "status": status
    }
    
    try:
        json_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            target_url,
            data=json_bytes,
            headers={
                'Content-Type': 'application/json',
                'apikey': SERVICE_ROLE_KEY,
                'Authorization': f'Bearer {SERVICE_ROLE_KEY}',
                'Prefer': 'return=minimal'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.getcode() in (200, 201)
    except Exception as e:
        print(f"[AUTH ERROR] Failed to commit new API key to Supabase: {e}")
        return False


# --- WHOIS SYNCHRONOUS HELPER FUNCTION ---
def perform_whois_lookup(domain_name):
    """
    Executes the synchronous WHOIS library logic and returns a structured dictionary.
    """
    try:
        domain_info = whois.whois(domain_name)
        if domain_info.registrar or domain_info.creation_date:
            return {
                "available": False,
                "status": "TAKEN",
                "registrar": domain_info.registrar,
                "domain": domain_name
            }
        else:
            return {
                "available": True,
                "status": "AVAILABLE",
                "registrar": None,
                "domain": domain_name
            }
    except whois.parser.PywhoisError:
        return {
            "available": True,
            "status": "AVAILABLE",
            "registrar": None,
            "domain": domain_name
        }
    except Exception as e:
        return {
            "available": False,
            "status": "ERROR",
            "message": str(e),
            "domain": domain_name
        }


@app.route('/')
def index():
    browser.ensure_background_loop_is_alive()
    return jsonify({
        "status": "ONLINE", 
        "message": "HostAfrica HTTP Automation Engine Running"
    }), 200


@app.route('/healthz')
def keep_alive_health_check():
    browser.ensure_background_loop_is_alive()
    return jsonify({"status": "HEALTHY"}), 200


@app.route('/api/reg_auth', methods=['POST'])
def generate_auth_key():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    status = data.get('status', 'paid').strip()

    if not username:
        return jsonify({"status": "ERROR", "message": "Missing required parameter: 'username'"}), 400

    chars = string.ascii_letters + string.digits
    api_key = ''.join(random.choice(chars) for _ in range(10))

    db_success = save_api_key_to_supabase(username, api_key, status)
    
    if not db_success:
        return jsonify({"status": "ERROR", "message": "Failed to persist authentication key inside backend storage."}), 500

    return jsonify({
        "status": "SUCCESS",
        "username": username,
        "api_key": api_key,
        "message": "API key issued successfully."
    }), 201


@app.route('/api/register', methods=['POST'])
def start_background_registration():
    """
    Fire-and-forget HTTP endpoint. Verifies API key context and username 
    against Supabase database schemas before spawning background automation pipeline loops.
    """
    data = request.get_json() or {}
    
    auth_username = data.get('username', '').strip()
    if not auth_username:
        return jsonify({"status": "ERROR", "message": "Missing required authentication validator field: 'username'"}), 400

    client_api_key = request.headers.get('X-API-Key')
    if not client_api_key or not verify_api_key_in_supabase(client_api_key, auth_username):
        return jsonify({"status": "UNAUTHORIZED", "message": "Invalid, expired, or mismatched username and X-API-Key token combination."}), 401

    browser.ensure_background_loop_is_alive()
    bg_loop = browser.get_loop()
    
    if not bg_loop or not bg_loop.is_running():
        return jsonify({"status": "ERROR", "message": "Background automation engine loop offline."}), 500

    custom_domain = data.get('domain', '').strip()
    first_name = data.get('first_name', 'ben').strip()
    last_name = data.get('last_name', 'dover').strip()
    custom_email = data.get('email', '').strip()
    custom_password = data.get('password', '').strip()
    custom_phone = data.get('phone', '+254712345678').strip()
    payment_method = data.get('payment_method', 'stk').strip()

    if not custom_domain:
        return jsonify({"status": "ERROR", "message": "Missing required field parameter: 'domain'"}), 400
        
    if not custom_email:
        custom_email = f"dummy_{random.randint(100,999)}@gmail.com"
    if not custom_password:
        custom_password = f"Pass_{random.randint(10000,99999)}!"

    if "@gmail.com" in custom_email.lower() and "+" not in custom_email:
        parts = custom_email.split('@')
        custom_email = f"{parts[0]}+{int(time.time()) % 1000000:06d}@{parts[1]}"

    price_metrics = match_pricing_for_domain(custom_domain)

    task_id = str(uuid.uuid4())
    
    with tasks_lock:
        ACTIVE_TASKS[task_id] = {
            "status": "PROCESSING",
            "domain": custom_domain,
            "category": price_metrics["category"],
            "registration_price": price_metrics["registration_price"],
            "renewal_price": price_metrics["renewal_price"],
            "started_at": int(time.time()),
            "error": None
        }

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        browser.stream_integrated_workflow(
            log_queue, auth_username, custom_domain, first_name, last_name, 
            custom_email, custom_phone, custom_password, payment_method
        ),
        bg_loop
    )

    def monitor_task_completion(tid, queue):
        async def _read_queue_stream():
            try:
                while True:
                    log_line = await queue.get()
                    with tasks_lock:
                        if tid not in ACTIVE_TASKS:
                            break
                        if log_line == "DONE":
                            if ACTIVE_TASKS[tid]["status"] == "PROCESSING":
                                ACTIVE_TASKS[tid]["status"] = "FINISHED"
                            break
                        elif "FINAL_RESULT:" in log_line:
                            ACTIVE_TASKS[tid]["status"] = "SUCCESS"
                        elif "[CRITICAL FAILURE]" in log_line:
                            ACTIVE_TASKS[tid]["status"] = "FAILED"
                            ACTIVE_TASKS[tid]["error"] = log_line
            except Exception as e:
                with tasks_lock:
                    if tid in ACTIVE_TASKS:
                        ACTIVE_TASKS[tid]["status"] = "FAILED"
                        ACTIVE_TASKS[tid]["error"] = f"Monitor internal failure: {str(e)}"
        
        asyncio.run_coroutine_threadsafe(_read_queue_stream(), bg_loop)

    monitor_task_completion(task_id, log_queue)

    return jsonify({
        "status": "ACCEPTED",
        "message": "Automation pipeline spawned successfully in background loop worker thread.",
        "task_id": task_id,
        "expected_database_domain": custom_domain,
        "pricing": price_metrics
    }), 202


@app.route('/api/status/<string:task_id>', methods=['GET'])
def check_task_status(task_id):
    with tasks_lock:
        task = ACTIVE_TASKS.get(task_id)
    if not task:
        return jsonify({"status": "NOT_FOUND", "message": "No transaction log footprints for this ID."}), 404
    return jsonify(task), 200


@app.route('/api/domain_lookup', methods=['GET'])
def lookup_domain_record():
    """
    Secure endpoint to fetch structural transaction updates directly from the 
    Supabase domain_records matrix layout. Requires username, domain, and a matching valid API key.
    Calculates dynamic compound objects and live countdown timers on-the-fly.
    """
    username = request.args.get('username', '').strip()
    domain = request.args.get('domain', '').strip()
    client_api_key = request.headers.get('X-API-Key')

    if not username or not domain:
        return jsonify({"status": "ERROR", "message": "Missing required query string fields: 'username' and 'domain'"}), 400

    if not client_api_key or not verify_api_key_in_supabase(client_api_key, username):
        return jsonify({"status": "UNAUTHORIZED", "message": "Invalid, missing, or mismatched authentication context credentials."}), 401

    target_url = f"{SUPABASE_URL}/rest/v1/domain_records?username=eq.{urllib.parse.quote(username)}&domain=eq.{urllib.parse.quote(domain)}&select=*"

    try:
        req = urllib.request.Request(
            target_url,
            headers={
                'apikey': SERVICE_ROLE_KEY,
                'Authorization': f'Bearer {SERVICE_ROLE_KEY}'
            },
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            records = json.loads(response.read().decode('utf-8'))
            
            if not records:
                return jsonify({"status": "NOT_FOUND", "message": f"No active data row footprints registered for domain '{domain}' under user context."}), 404
                
            processed_records = []
            now_ts = int(time.time())
            
            for item in records:
                # 1. Parse created_at timestamp securely to handle ISO formatting variants
                # Stripe out potential 'Z' suffix and split at timezone offset if present
                raw_created = item.get("created_at", "")
                try:
                    clean_created = raw_created.replace("Z", "").split("+")[0]
                    dt_created = datetime.fromisoformat(clean_created).replace(tzinfo=timezone.utc)
                    created_ts = int(dt_created.timestamp())
                except Exception:
                    # Fallback structural calculation strategy using item's primary integer timestamp
                    created_ts = item.get("timestamp", now_ts)
                
                # 2. Calculate Domain Availability Time Horizon (exactly 3 minutes after creation)
                available_in_ts = created_ts + 180
                time_remaining = available_in_ts - now_ts
                if time_remaining < 0:
                    time_remaining = 0
                
                # 3. Assemble composite objects and clean up standalone parameters
                email = item.pop("email", None)
                password = item.pop("password", None)
                
                computed_item = {
                    "id": item.get("id"),
                    "domain": item.get("domain"),
                    "invoice_id": item.get("invoice_id"),
                    "invoice_url": item.get("invoice_url"),
                    "login_credentials": {
                        "email": email,
                        "password": password
                    },
                    "registration_price": item.get("registration_price"),
                    "renewal_price": item.get("renewal_price"),
                    "category": item.get("category"),
                    "payment_method": item.get("payment_method"),
                    "status": item.get("status"),
                    "username": item.get("username"),
                    "time_created": raw_created,
                    "timestamp": item.get("timestamp"),
                    "domain_available_in": datetime.fromtimestamp(available_in_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    "time_remaining_seconds": time_remaining
                }
                processed_records.append(computed_item)

            return jsonify({
                "status": "SUCCESS",
                "count": len(processed_records),
                "data": processed_records
            }), 200

    except Exception as e:
        print(f"[LOOKUP ERROR] Direct backend database mapping access failed: {e}")
        return jsonify({"status": "ERROR", "message": f"Supabase sync target dropped: {str(e)}"}), 500


@app.route('/api/check_available', methods=['POST'])
def check_domain_availability_endpoint():
    """
    Synchronous WHOIS query container wrapped inside async executors 
    to verify domain state layout footprint across external registration spaces.
    Adds parsed static price attributes directly onto output response payloads.
    """
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()

    if not domain:
        return jsonify({"status": "ERROR", "message": "Missing required parameter: 'domain'"}), 400

    browser.ensure_background_loop_is_alive()
    bg_loop = browser.get_loop()

    if not bg_loop or not bg_loop.is_running():
        return jsonify({"status": "ERROR", "message": "Background worker engine offline."}), 500

    try:
        async def async_wrapper():
            return await bg_loop.run_in_executor(None, perform_whois_lookup, domain)

        future = asyncio.run_coroutine_threadsafe(async_wrapper(), bg_loop)
        result = future.result(timeout=15)
        
        if result.get("status") == "ERROR":
            return jsonify({"status": "ERROR", "message": f"Could not verify domain: {result.get('message')}"}), 500
            
        # Append fixed registration and renewal matrix configurations directly to payload response
        price_metrics = match_pricing_for_domain(domain)
        result["category"] = price_metrics["category"]
        result["registration_price"] = price_metrics["registration_price"]
        result["renewal_price"] = price_metrics["renewal_price"]
            
        return jsonify(result), 200

    except Exception as e:
        print(f"[WHOIS ERROR] External network context pipeline timing failed: {e}")
        return jsonify({"status": "ERROR", "message": f"WHOIS operational cycle timed out or failed: {str(e)}"}), 500


if __name__ == "__main__":
    browser.ensure_background_loop_is_alive()
    
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Launching Fixed-Price HTTP Execution Gateway on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

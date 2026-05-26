import os
import random
import time
import asyncio
import uuid
import string
import json
import urllib.request
from threading import Lock
from flask import Flask, request, jsonify
from flask_cors import CORS  # Handles cross-origin resource sharing

# Import your monolithic background driver
import browser

app = Flask(__name__)

# --- ENABLE CORS ENGINE CORE ---
# This allows external client applications (like your PHP frontend) 
# to talk to your API endpoints without triggering browser blockades.
CORS(app, resources={r"/api/*": {"origins": "*"}}, allow_headers=["Content-Type", "X-API-Key"])

# Global tracking structures with explicit Thread Locking
ACTIVE_TASKS = {}
tasks_lock = Lock()

# Supabase Configurations for API Key checks
SUPABASE_URL = "https://zeccnkbazpqjztjrifsx.supabase.co"
SERVICE_ROLE_KEY = "sb_secret_xtVXHEqfMyEkeuSoob8sKw_awiu8BEH"


def verify_api_key_in_supabase(api_key):
    """
    Queries the api_keys table directly via the REST interface 
    to see if the provided key exists and is valid.
    """
    if not api_key:
        return False
        
    target_url = f"{SUPABASE_URL}/rest/v1/api_keys?api_key=eq.{api_key}&status=eq.paid&select=*"
    
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
    Saves a newly generated API key structural footprint into Supabase.
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
    """
    Accepts username and status, generates a unique 10-digit 
    alphanumeric API key, and commits it to the database matrix.
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    status = data.get('status', 'paid').strip()

    if not username:
        return jsonify({"status": "ERROR", "message": "Missing required parameter: 'username'"}), 400

    # Generate a random 10-digit alphanumeric key
    chars = string.ascii_letters + string.digits
    api_key = ''.join(random.choice(chars) for _ in range(10))

    # Commit metadata footprint down to Supabase storage structures
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
    Fire-and-forget HTTP endpoint. Spawns browser loop immediately.
    Enforces API key confirmation via headers before granting entry.
    """
    # Enforce API Key Authentication verification gateway
    client_api_key = request.headers.get('X-API-Key')
    if not client_api_key or not verify_api_key_in_supabase(client_api_key):
        return jsonify({"status": "UNAUTHORIZED", "message": "Invalid, expired, or missing X-API-Key token context."}), 401

    browser.ensure_background_loop_is_alive()
    bg_loop = browser.get_loop()
    
    if not bg_loop or not bg_loop.is_running():
        return jsonify({"status": "ERROR", "message": "Background automation engine loop offline."}), 500

    data = request.get_json() or {}
    
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

    task_id = str(uuid.uuid4())
    
    with tasks_lock:
        ACTIVE_TASKS[task_id] = {
            "status": "PROCESSING",
            "domain": f"{custom_domain}.co.ke",
            "started_at": int(time.time()),
            "error": None
        }

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        browser.stream_integrated_workflow(
            log_queue, custom_domain, first_name, last_name, 
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
        "expected_database_domain": f"{custom_domain}.co.ke"
    }), 202


@app.route('/api/status/<string:task_id>', methods=['GET'])
def check_task_status(task_id):
    with tasks_lock:
        task = ACTIVE_TASKS.get(task_id)
    if not task:
        return jsonify({"status": "NOT_FOUND", "message": "No transaction log footprints for this ID."}), 404
    return jsonify(task), 200


if __name__ == "__main__":
    browser.ensure_background_loop_is_alive()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Launching Background HTTP Execution Gateway on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

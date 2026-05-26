import os
import random
import time
import asyncio
import uuid
from flask import Flask, request, jsonify

# Import your monolithic background driver
import browser

app = Flask(__name__)

# Global in-memory dictionary to track background job execution status
ACTIVE_TASKS = {}

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


@app.route('/api/register', methods=['POST'])
def start_background_registration():
    """
    Fire-and-forget HTTP endpoint. 
    Spawns the headless browser automation loop and immediately returns a tracking ID.
    """
    browser.ensure_background_loop_is_alive()
    bg_loop = browser.get_loop()
    
    if not bg_loop or not bg_loop.is_running():
        return jsonify({"status": "ERROR", "message": "Background automation engine loop offline."}), 500

    # Handle optional JSON input payload comfortably
    data = request.get_json() or {}
    
    custom_domain = data.get('domain', '').strip()
    first_name = data.get('first_name', 'ben').strip()
    last_name = data.get('last_name', 'dover').strip()
    custom_email = data.get('email', '').strip()
    custom_password = data.get('password', '').strip()
    custom_phone = data.get('phone', '+254712345678').strip()
    payment_method = data.get('payment_method', 'stk').strip()

    # Core constraint verification
    if not custom_domain:
        return jsonify({"status": "ERROR", "message": "Missing required field parameter: 'domain'"}), 400
        
    # Auto-generation fallbacks
    if not custom_email:
        custom_email = f"dummy_{random.randint(100,999)}@gmail.com"
    if not custom_password:
        custom_password = f"Pass_{random.randint(10000,99999)}!"

    # Dynamic Gmail sub-addressing tokenization matrix
    if "@gmail.com" in custom_email.lower() and "+" not in custom_email:
        parts = custom_email.split('@')
        username_part = parts[0]
        domain_name_part = parts[1]
        
        epoch_secs = int(time.time())
        unique_token = epoch_secs % 1000000
        unique_token_str = f"{unique_token:06d}"
        
        custom_email = f"{username_part}+{unique_token_str}@{domain_name_part}"

    # Generate a unique asynchronous tracking engine UUID
    task_id = str(uuid.uuid4())
    ACTIVE_TASKS[task_id] = {
        "status": "PROCESSING",
        "domain": f"{custom_domain}.co.ke",
        "started_at": int(time.time()),
        "error": None
    }

    # Thread-safe log collection container
    log_queue = asyncio.Queue()

    # Dispatch workflow into background engine thread and release client HTTP pipeline immediately
    asyncio.run_coroutine_threadsafe(
        browser.stream_integrated_workflow(
            log_queue, custom_domain, first_name, last_name, 
            custom_email, custom_phone, custom_password, payment_method
        ),
        bg_loop
    )

    # In-memory tracking monitor that watches the queue state without blocking
    def monitor_task_completion(tid, queue):
        async def _read_queue_stream():
            while True:
                log_line = await queue.get()
                if log_line == "DONE":
                    if ACTIVE_TASKS[tid]["status"] == "PROCESSING":
                        ACTIVE_TASKS[tid]["status"] = "FINISHED"
                    break
                elif "FINAL_RESULT:" in log_line:
                    ACTIVE_TASKS[tid]["status"] = "SUCCESS"
                elif "[CRITICAL FAILURE]" in log_line:
                    ACTIVE_TASKS[tid]["status"] = "FAILED"
                    ACTIVE_TASKS[tid]["error"] = log_line
        
        asyncio.run_coroutine_threadsafe(_read_queue_stream(), bg_loop)

    monitor_task_completion(task_id, log_queue)

    # Return immediate 202 Accepted delivery receipt context
    return jsonify({
        "status": "ACCEPTED",
        "message": "Automation pipeline spawned successfully in background loop worker thread.",
        "task_id": task_id,
        "expected_database_domain": f"{custom_domain}.co.ke"
    }), 202


@app.route('/api/status/<string:task_id>', methods=['GET'])
def check_task_status(task_id):
    """
    Optional endpoint to fetch local state memory mapping 
    before parsing downstream Supabase DB structures.
    """
    task = ACTIVE_TASKS.get(task_id)
    if not task:
        return jsonify({"status": "NOT_FOUND", "message": "No transaction log footprints for this ID."}), 404
    return jsonify(task), 200


if __name__ == "__main__":
    browser.ensure_background_loop_is_alive()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Launching Background HTTP Execution Gateway on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

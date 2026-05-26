import os
import random
import time
import asyncio
from flask import Flask, request, jsonify
from flask_sock import Sock

# Import your monolithic background driver
import browser

app = Flask(__name__)
sock = Sock(app)

@app.route('/')
def index():
    browser.ensure_background_loop_is_alive()
    return jsonify({"status": "ONLINE", "message": "HostAfrica Automation Engine Running"}), 200

@app.route('/healthz')
def keep_alive_health_check():
    browser.ensure_background_loop_is_alive()
    return jsonify({"status": "HEALTHY"}), 200


@sock.route('/ws/stream')
def logs_websocket_stream_endpoint(ws):
    browser.ensure_background_loop_is_alive()
    bg_loop = browser.get_loop()
    if not bg_loop or not bg_loop.is_running():
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
        username_part = parts[0]
        domain_name_part = parts[1]
        
        epoch_secs = int(time.time())
        unique_token = epoch_secs % 1000000
        unique_token_str = f"{unique_token:06d}"
        
        custom_email = f"{username_part}+{unique_token_str}@{domain_name_part}"

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        browser.stream_integrated_workflow(log_queue, custom_domain, first_name, last_name, custom_email, custom_phone, custom_password, payment_method),
        bg_loop
    )

    while True:
        future = asyncio.run_coroutine_threadsafe(log_queue.get(), bg_loop)
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
    browser.ensure_background_loop_is_alive()
    bg_loop = browser.get_loop()
    if not bg_loop or not bg_loop.is_running():
        ws.send("ERROR: Background environment loop offline.")
        return

    custom_domain = request.args.get('domain', '').strip()
    if not custom_domain:
        ws.send("ERROR: Missing required 'domain' tracking parameter query string.")
        ws.send("DONE")
        return

    log_queue = asyncio.Queue()

    asyncio.run_coroutine_threadsafe(
        browser.stream_domain_check_workflow(log_queue, custom_domain),
        bg_loop
    )

    while True:
        future = asyncio.run_coroutine_threadsafe(log_queue.get(), bg_loop)
        log_line = future.result()
        
        try:
            ws.send(log_line)
        except Exception:
            print("[*] Scan tracking connection disconnected by programmatic consumer interface client.")
            break
            
        if log_line == "DONE":
            break


if __name__ == "__main__":
    browser.ensure_background_loop_is_alive()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Launching local Flask Server Engine on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

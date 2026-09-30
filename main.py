import os
import json
import asyncio
from flask import Flask, render_template_string
from flask_sock import Sock
from flask_cors import CORS
from playwright.async_api import async_playwright

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# Local Pinggy HTTP proxy tunnel URL
# Replace with your current active Pinggy URL, or pass via environment variable
LOCAL_HOME_PROXY = os.environ.get(
    "LOCAL_HOME_PROXY", 
    "https://lszxs-197-237-36-88.free.pinggy.net"
)

# Embedded Single-Page Client App
HTML_CLIENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Remote Cloud Browser</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; display: flex; flex-direction: column; align-items: center; min-height: 100vh; padding: 20px; }
        .toolbar { display: flex; gap: 10px; width: 100%; max-width: 1280px; margin-bottom: 15px; }
        input[type="text"] { flex: 1; padding: 12px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #fff; font-size: 15px; outline: none; }
        input[type="text"]:focus { border-color: #3b82f6; }
        button { padding: 12px 24px; border-radius: 8px; border: none; background: #2563eb; color: #fff; font-weight: 600; cursor: pointer; transition: background 0.2s, opacity 0.2s; }
        button:hover { background: #1d4ed8; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        
        .btn-proxy-off { background: #475569; }
        .btn-proxy-off:hover { background: #334155; }
        .btn-proxy-on { background: #16a34a; }
        .btn-proxy-on:hover { background: #15803d; }

        .canvas-container { position: relative; width: 100%; max-width: 1280px; background: #000; border-radius: 12px; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
        canvas { width: 100%; height: auto; display: block; cursor: crosshair; }
        .status { position: absolute; top: 10px; right: 10px; background: rgba(15, 23, 42, 0.85); padding: 6px 14px; border-radius: 20px; font-size: 12px; backdrop-filter: blur(4px); border: 1px solid #334155; }
    </style>
</head>
<body>

    <div class="toolbar">
        <input type="text" id="urlInput" placeholder="Enter URL (e.g., https://news.ycombinator.com)" value="https://news.ycombinator.com">
        <button onclick="navigate()">Go</button>
        <button id="proxyBtn" class="btn-proxy-off" onclick="toggleProxy()">Proxy: OFF (Render IP)</button>
    </div>

    <div class="canvas-container">
        <div class="status" id="statusTag">Connecting...</div>
        <canvas id="browserCanvas" width="1280" height="720"></canvas>
    </div>

    <script>
        const canvas = document.getElementById('browserCanvas');
        const ctx = canvas.getContext('2d');
        const statusTag = document.getElementById('statusTag');
        const urlInput = document.getElementById('urlInput');
        const proxyBtn = document.getElementById('proxyBtn');

        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${wsProtocol}//${location.host}/ws`);
        ws.binaryType = 'arraybuffer';

        let useLocalProxy = false;

        ws.onopen = () => {
            statusTag.textContent = 'Connected (Live)';
            statusTag.style.color = '#4ade80';
        };

        ws.onclose = () => {
            statusTag.textContent = 'Disconnected';
            statusTag.style.color = '#f87171';
        };

        ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                const blob = new Blob([event.data], { type: 'image/jpeg' });
                const img = new Image();
                img.onload = () => {
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                    URL.revokeObjectURL(img.src);
                };
                img.src = URL.createObjectURL(blob);
            }
        };

        function getNormalizedCoords(e) {
            const rect = canvas.getBoundingClientRect();
            return {
                x: (e.clientX - rect.left) / rect.width,
                y: (e.clientY - rect.top) / rect.height
            };
        }

        let lastMove = 0;
        canvas.addEventListener('mousemove', (e) => {
            const now = Date.now();
            if (now - lastMove > 50) { // Throttle to 20 updates/sec
                const { x, y } = getNormalizedCoords(e);
                ws.send(JSON.stringify({ type: 'mousemove', x, y }));
                lastMove = now;
            }
        });

        canvas.addEventListener('click', (e) => {
            const { x, y } = getNormalizedCoords(e);
            ws.send(JSON.stringify({ type: 'click', x, y }));
        });

        window.addEventListener('keydown', (e) => {
            if (e.key.length === 1 || ['Enter', 'Backspace', 'Tab', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
                ws.send(JSON.stringify({ type: 'keydown', key: e.key }));
            }
        });

        function navigate() {
            let url = urlInput.value.trim();
            if (!url.startsWith('http://') && !url.startsWith('https://')) {
                url = 'https://' + url;
            }
            ws.send(JSON.stringify({ type: 'navigate', url: url }));
        }

        function toggleProxy() {
            useLocalProxy = !useLocalProxy;
            proxyBtn.disabled = true;
            
            if (useLocalProxy) {
                proxyBtn.textContent = 'Switching to Proxy...';
                proxyBtn.className = 'btn-proxy-on';
            } else {
                proxyBtn.textContent = 'Switching to Render IP...';
                proxyBtn.className = 'btn-proxy-off';
            }

            ws.send(JSON.stringify({ type: 'toggle_proxy', enabled: useLocalProxy }));

            setTimeout(() => {
                proxyBtn.disabled = false;
                if (useLocalProxy) {
                    proxyBtn.textContent = 'Proxy: ON (Home IP)';
                } else {
                    proxyBtn.textContent = 'Proxy: OFF (Render IP)';
                }
            }, 1500);
        }

        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') navigate();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_CLIENT)

async def handle_browser_session(ws):
    """Async engine managing Playwright inside Flask-Sock's synchronous WebSocket wrapper."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        
        is_proxy_enabled = False

        async def create_new_context(use_proxy=False):
            proxy_config = None
            if use_proxy:
                proxy_config = {"server": LOCAL_HOME_PROXY}
            
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                proxy=proxy_config
            )
            page = await context.new_page()
            return context, page

        context, page = await create_new_context(use_proxy=False)
        await page.goto("https://news.ycombinator.com")

        stop_signal = False

        # Task 1: Frame broadcasting loop (~12 FPS)
        async def stream_frames():
            nonlocal stop_signal
            try:
                while not stop_signal:
                    if page and not page.is_closed():
                        frame = await page.screenshot(type="jpeg", quality=45)
                        ws.send(frame)
                    await asyncio.sleep(0.08)
            except Exception:
                stop_signal = True

        # Task 2: Incoming event loop
        async def process_inputs():
            nonlocal stop_signal, context, page, is_proxy_enabled
            loop = asyncio.get_running_loop()
            try:
                while not stop_signal:
                    # Offload blocking WebSocket receive to executor to keep async loop fluid
                    raw_data = await loop.run_in_executor(None, ws.receive)
                    if raw_data is None:
                        stop_signal = True
                        break

                    event = json.loads(raw_data)
                    event_type = event.get("type")

                    if event_type == "toggle_proxy":
                        new_state = event.get("enabled", False)
                        if new_state != is_proxy_enabled:
                            is_proxy_enabled = new_state
                            current_url = page.url
                            await context.close()
                            context, page = await create_new_context(use_proxy=is_proxy_enabled)
                            if current_url and current_url != "about:blank":
                                await page.goto(current_url)

                    elif event_type == "navigate":
                        await page.goto(event["url"], timeout=30000)

                    elif event_type == "click":
                        x = int(event.get("x", 0) * 1280)
                        y = int(event.get("y", 0) * 720)
                        await page.mouse.click(x, y)

                    elif event_type == "mousemove":
                        x = int(event.get("x", 0) * 1280)
                        y = int(event.get("y", 0) * 720)
                        await page.mouse.move(x, y)

                    elif event_type == "keydown":
                        await page.keyboard.press(event["key"])

            except Exception:
                stop_signal = True

        await asyncio.gather(stream_frames(), process_inputs(), return_exceptions=True)
        await browser.close()

@sock.route('/ws')
def remote_browser_ws(ws):
    """Bridge Flask-Sock synchronous handler to Python's asyncio event loop."""
    asyncio.run(handle_browser_session(ws))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

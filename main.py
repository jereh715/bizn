import requests
from flask import Flask
import os

app = Flask(__name__)

# The most basic headers to look like a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

@app.route('/')
def home():
    return "Tester is online. Go to /curl to see Jiji output.", 200

@app.route('/curl')
def curl_jiji():
    target = "https://jiji.co.ke"
    print(f"[*] Attempting to curl {target}...")
    try:
        # We use a 20 second timeout to give Render's network plenty of time
        res = requests.get(target, headers=HEADERS, timeout=20)
        
        # Check the status code
        status = res.status_code
        print(f"[*] Status Received: {status}")

        if status == 200:
            # Send the first 2000 characters of HTML to your browser
            import html
            snippet = html.escape(res.text[:2000])
            return f"<h1>Success! Status: {status}</h1><pre>{snippet}</pre>", 200
        else:
            return f"<h1>Failed. Status: {status}</h1><p>Jiji is blocking the request.</p>", status

    except Exception as e:
        print(f"[!] Error: {str(e)}")
        return f"<h1>Connection Error</h1><p>{str(e)}</p>", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

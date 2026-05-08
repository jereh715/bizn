import requests
from flask import Flask
import os
import html

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

@app.route('/')
def home():
    return "Tester Online. Visit /curl to check Jiji.", 200

@app.route('/curl')
def curl_test():
    url = "https://jiji.co.ke"
    try:
        # We try to get the page
        res = requests.get(url, headers=HEADERS, timeout=15)
        
        # We check the status
        status = res.status_code
        
        # We get the first 1000 characters of whatever Jiji sent
        content = html.escape(res.text[:1000])
        
        return f"""
        <h1>Status: {status}</h1>
        <p>If status is 403, Render is blocked by Jiji's Firewall.</p>
        <hr>
        <h3>Raw Content Snippet:</h3>
        <pre>{content}</pre>
        """
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

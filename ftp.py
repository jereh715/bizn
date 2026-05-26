import urllib.request
import json

# --- TARGET CONFIGURATION ---
SECRET_KEY = "Mambus_Secure_Vault_2026_Tokens"
# We append the key straight to the URL so firewalls cannot strip it out
API_ENDPOINT_URL = f"http://bizna.store/pay/index.php?auth={SECRET_KEY}" 

def append_domain_record(payload):
    """
    Bypasses FTP timeouts and custom header stripping filters by routing
    transaction parameters directly to the index url query string parameters.
    """
    print(f"[*] Dispatching secure query web storage handshake to index for: {payload.get('domain')}")
    
    try:
        # Convert payload dictionary to raw JSON bytes
        json_bytes = json.dumps(payload).encode('utf-8')
        
        # Build the standard request block with core standard content-type header
        req = urllib.request.Request(
            API_ENDPOINT_URL,
            data=json_bytes,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'Render-Automation-Engine'
            },
            method='POST'
        )
        
        # Dispatch request with a safe 15-second tracking timeout boundary
        with urllib.request.urlopen(req, timeout=15) as response:
            response_body = response.read().decode('utf-8')
            response_data = json.loads(response_body)
            
            if response_data.get("status") == "SUCCESS":
                print("[SUCCESS] HTTP Storage Synchronization Complete via URL query routing.")
                return True
            else:
                print(f"[STORAGE ERROR] index.php endpoint rejected sync: {response_data.get('message')}")
                return False
                
    except Exception as http_err:
        print(f"[STORAGE ROUTING COLLAPSED] Web API query route handshake failed: {http_err}")
        return False

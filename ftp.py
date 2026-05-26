import urllib.request
import json

# --- TARGET CONFIGURATION ---
# Replace this with your actual website domain address where sync_record.php is saved
API_ENDPOINT_URL = "http://bizna.store/pay/index.php" 
SECRET_KEY = "Mambus_Secure_Vault_2026_Tokens"

def append_domain_record(payload):
    """
    Bypasses FTP network timeouts completely by routing transaction metrics
    straight to your website's custom backend storage API endpoint.
    """
    print(f"[*] Dispatching secure web storage API handshake for: {payload.get('domain')}")
    
    try:
        # Convert payload dictionary to raw JSON bytes
        json_bytes = json.dumps(payload).encode('utf-8')
        
        # Build the standard request block with your authentication headers
        req = urllib.request.Request(
            API_ENDPOINT_URL,
            data=json_bytes,
            headers={
                'Content-Type': 'application/json',
                'X-Storage-Auth': SECRET_KEY,
                'User-Agent': 'Render-Automation-Engine'
            },
            method='POST'
        )
        
        # Dispatch request with a safe 15-second tracking timeout boundary
        with urllib.request.urlopen(req, timeout=15) as response:
            response_body = response.read().decode('utf-8')
            response_data = json.loads(response_body)
            
            if response_data.get("status") == "SUCCESS":
                print("[SUCCESS] HTTP Storage Synchronization Complete.")
                return True
            else:
                print(f"[STORAGE ERROR] Web API endpoint rejected sync: {response_data.get('message')}")
                return False
                
    except Exception as http_err:
        print(f"[STORAGE ROUTING COLLAPSED] Web API route handshake failed: {http_err}")
        return False

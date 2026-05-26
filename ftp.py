import ftplib
import io
import json
import time

# --- CONFIGURATION ---
FTP_HOST = "ftpupload.net"
FTP_USER = "bizna_41810217"
FTP_PASS = "viuowgbs"

def append_domain_record(payload):
    """
    Connects to the remote FTP server, downloads 'htdocs/domains.json',
    appends the new domain buyer/invoice dataset, and saves it back.
    
    This keeps the storage file in the root web directory to match the 
    permissions and file visibility of your cloud editor app.
    """
    print(f"[*] Connecting to remote storage for: {payload.get('domain')}")
    
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)
        
        # 1. Navigate directly to the public web folder
        try:
            ftp.cwd('htdocs')
        except Exception as e:
            print(f"[FTP Storage] Warning: Could not change directory to htdocs: {e}")
        
        # 2. Download the existing domains.json file if it exists
        current_records = []
        try:
            memory_buffer = io.BytesIO()
            ftp.retrbinary("RETR domains.json", memory_buffer.write)
            
            # Parse historical JSON records
            raw_content = memory_buffer.getvalue().decode('utf-8').strip()
            if raw_content:
                current_records = json.loads(raw_content)
                if not isinstance(current_records, list):
                    current_records = [current_records]
        except Exception:
            print("[FTP Storage] domains.json not found in htdocs or empty. Initializing new array template.")
            current_records = []

        # 3. Append the new buyer details and registration invoice data
        current_records.append(payload)
        
        # 4. Convert the updated data back to formatted JSON and upload it
        updated_json_bytes = json.dumps(current_records, indent=4).encode('utf-8')
        upload_buffer = io.BytesIO(updated_json_bytes)
        
        ftp.storbinary("STOR domains.json", upload_buffer)
        print("[SUCCESS] Data synchronized cleanly with htdocs/domains.json")
        
        ftp.quit()
        return True
        
    except Exception as e:
        print(f"[FTP ERROR] Failed to save storage state: {e}")
        return False

# --- SELF-TEST BLOCK (Optional testing via command line) ---
if __name__ == "__main__":
    print("[*] Running local script connection sanity check...")
    sample_payload = {
        "status": "TEST_RUN",
        "domain": "test-connection.co.ke",
        "email": "test@gmail.com",
        "password": "TestPassword123!",
        "invoice_url": "https://my.hostafrica.com/viewinvoice.php?id=000000",
        "invoice_id": "000000",
        "payment_method": "manual",
        "timestamp": int(time.time())
    }
    append_domain_record(sample_payload)

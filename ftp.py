import ftplib
import io
import json
import time

FTP_HOST = "ftpupload.net"
FTP_USER = "bizna_41810217"
FTP_PASS = "viuowgbs"

def append_domain_record(payload):
    """
    Connects to the FTP server, downloads 'htdocs/data/domains.json',
    appends the new domain buyer/invoice data, and saves it back.
    """
    print(f"[*] Connecting to remote storage for: {payload.get('domain')}")
    
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)
        
        # 1. Navigate to the public web folder
        try:
            ftp.cwd('htdocs')
        except Exception:
            pass
        
        # 2. Ensure the 'data' subfolder exists, then move into it
        try:
            ftp.cwd('data')
        except Exception:
            print("[FTP Storage] 'data' directory not found. Creating it...")
            ftp.mkd('data')
            ftp.cwd('data')
            
        # 3. Download the existing domains.json file if it exists
        current_records = []
        try:
            memory_buffer = io.BytesIO()
            ftp.retrbinary("RETR domains.json", memory_buffer.write)
            
            # Parse existing JSON data
            raw_content = memory_buffer.getvalue().decode('utf-8').strip()
            if raw_content:
                current_records = json.loads(raw_content)
                if not isinstance(current_records, list):
                    current_records = [current_records]
        except Exception:
            print("[FTP Storage] domains.json not found or empty. Initializing new list.")
            current_records = []

        # 4. Append the new buyer details and registration invoice data
        current_records.append(payload)
        
        # 5. Convert the updated data back to JSON format and upload it
        updated_json_bytes = json.dumps(current_records, indent=4).encode('utf-8')
        upload_buffer = io.BytesIO(updated_json_bytes)
        
        ftp.storbinary("STOR domains.json", upload_buffer)
        print("[SUCCESS] Data synchronized with htdocs/data/domains.json")
        
        ftp.quit()
        return True
        
    except Exception as e:
        print(f"[FTP ERROR] Failed to save storage state: {e}")
        return False

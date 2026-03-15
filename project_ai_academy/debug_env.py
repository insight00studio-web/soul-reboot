import os
from dotenv import load_dotenv

load_dotenv()
key = os.environ.get("GEMINI_API_KEY", "")
sid = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")

print(f"API_KEY_FOUND: {bool(key)}")
if key:
    print(f"API_KEY_LENGTH: {len(key)}")
print(f"SPREADSHEET_ID_FOUND: {bool(sid)}")

# Check service_account.json
sa_exists = os.path.exists("service_account.json")
print(f"SERVICE_ACCOUNT_EXISTS: {sa_exists}")

"""Google Sheets/Drive OAuth再認証スクリプト。update_token.ps1から呼び出される。"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds_path = sys.argv[1] if len(sys.argv) > 1 else "credentials.json"
token_path = sys.argv[2] if len(sys.argv) > 2 else "token.json"

flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
creds = flow.run_local_server(port=0)
with open(token_path, "w") as f:
    f.write(creds.to_json())
print("再認証成功！")

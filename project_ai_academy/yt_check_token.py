"""YouTubeトークンの有効性チェック。update_token.ps1から呼び出される。"""
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import json

try:
    creds = Credentials.from_authorized_user_file("youtube_token.json")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("youtube_token.json", "w") as f:
            f.write(creds.to_json())
        print("REFRESHED")
    else:
        print("VALID")
except Exception as e:
    print(f"INVALID:{e}")

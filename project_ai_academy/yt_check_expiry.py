"""YouTubeトークンの期限情報を表示。update_token.ps1から呼び出される。"""
import json
from datetime import datetime, timezone

try:
    with open("youtube_token.json") as f:
        t = json.load(f)
    expiry_str = t.get("expiry", "")
    if expiry_str:
        expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_left = (expiry - now).total_seconds() / 86400
        print(f"EXPIRY:{expiry_str}")
        print(f"DAYS:{days_left:.1f}")
    else:
        print("EXPIRY:unknown")
        print("DAYS:-1")
except Exception as e:
    print(f"ERROR:{e}")
    print("DAYS:-1")

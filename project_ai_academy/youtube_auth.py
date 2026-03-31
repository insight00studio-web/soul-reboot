"""
youtube_auth.py
Soul Reboot - YouTube API v3 共通認証モジュール

youtube_analytics.py と youtube_uploader.py から共通利用される。
"""

import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# 認証ファイル
BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
YOUTUBE_TOKEN_FILE = BASE_DIR / "youtube_token.json"

# YouTube Data API v3 スコープ（読み取り + アップロード共用）
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def get_youtube_client():
    """OAuth2認証を行い、YouTube APIクライアントを返す。

    初回実行時にブラウザが開き、Google アカウントでの認証が必要。
    以降は youtube_token.json にキャッシュされたトークンが自動的に使われる。
    """
    creds = None

    if YOUTUBE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(YOUTUBE_TOKEN_FILE), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[AUTH] トークンをリフレッシュ中...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: {CREDENTIALS_FILE} が見つかりません")
                sys.exit(1)
            print("[AUTH] ブラウザで認証してください...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(YOUTUBE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print("[AUTH] 認証成功。トークンを保存しました。")

    return build("youtube", "v3", credentials=creds)

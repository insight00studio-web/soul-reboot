"""
drive_auth.py
Soul Reboot - Google Drive API 共通認証モジュール
"""

import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
DRIVE_TOKEN_FILE = BASE_DIR / "drive_token.json"

# drive.file スコープ: このアプリが作成したファイルのみ操作可能
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_client():
    """OAuth2認証を行い、Google Drive APIクライアントを返す。

    初回実行時にブラウザが開き、Google アカウントでの認証が必要。
    以降は drive_token.json にキャッシュされたトークンが自動的に使われる。
    """
    creds = None

    if DRIVE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(DRIVE_TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[DRIVE AUTH] トークンをリフレッシュ中...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: {CREDENTIALS_FILE} が見つかりません")
                sys.exit(1)
            print("[DRIVE AUTH] ブラウザで認証してください...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(DRIVE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print("[DRIVE AUTH] 認証成功。トークンを保存しました。")

    return build("drive", "v3", credentials=creds)

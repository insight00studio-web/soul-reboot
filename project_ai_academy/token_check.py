"""
token_check.py
Soul Reboot - トークン有効性チェックスクリプト

Phase A の数時間前（JST 13:00）に実行し、問題があれば Gmail で通知する。
GitHub Actions の token_check.yml から呼び出される。
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def check_google_token(spreadsheet_id: str) -> tuple[bool, str]:
    """Google Sheets トークンの有効性チェック（実際に接続を試みる）"""
    try:
        from sheets_db import SoulRebootDB
        SoulRebootDB(spreadsheet_id)
        return True, "接続成功"
    except Exception as e:
        msg = str(e)
        if "invalid_grant" in msg or "Token has been expired" in msg:
            return False, "invalid_grant: リフレッシュトークンが失効しています"
        return False, f"接続エラー: {msg[:200]}"


def check_youtube_token() -> tuple[bool, str]:
    """YouTube トークンの有効性チェック（リフレッシュを試みる）"""
    token_path = BASE_DIR / "youtube_token.json"
    if not token_path.exists():
        return False, "youtube_token.json が見つかりません"
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = Credentials.from_authorized_user_file(str(token_path))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            return True, "リフレッシュ成功"
        elif not creds.valid:
            return False, "トークンが無効（リフレッシュトークンなし）"
        return True, "有効"
    except Exception as e:
        msg = str(e)
        if "invalid_grant" in msg:
            return False, "invalid_grant: YouTube 再認証が必要です"
        return False, f"エラー: {msg[:200]}"


def check_claude_token() -> tuple[bool, str]:
    """Claude OAuth トークンの存在確認（36〜48時間で失効するため要毎日更新）"""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if not token:
        return False, "CLAUDE_CODE_OAUTH_TOKEN が未設定です"
    # OAuth トークンは REST API では検証不可のため存在確認のみ
    # 有効期限は36〜48時間のため update_token.ps1 を毎日実行してください
    return True, "設定済み（有効期限36〜48時間 → update_token.ps1 を毎日実行）"


def main() -> None:
    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")

    results: list[tuple[str, bool, str]] = []

    # --- Google Sheets トークン ---
    if spreadsheet_id:
        ok, msg = check_google_token(spreadsheet_id)
        results.append(("Google Sheets トークン", ok, msg))
    else:
        results.append(("Google Sheets トークン", False, "SOUL_REBOOT_SPREADSHEET_ID が未設定"))

    # --- YouTube トークン ---
    ok, msg = check_youtube_token()
    results.append(("YouTube トークン", ok, msg))

    # --- Claude OAuth トークン ---
    ok, msg = check_claude_token()
    results.append(("Claude OAuth トークン", ok, msg))

    # --- 結果表示 ---
    has_error = False
    lines = ["=== Token Check Results ==="]
    for name, ok, msg in results:
        status = "OK   " if ok else "ERROR"
        lines.append(f"  [{status}] {name}: {msg}")
        if not ok:
            has_error = True

    report = "\n".join(lines)
    print(report)

    # --- エラー時はメール通知 ---
    if has_error:
        print("\n[NOTIFY] 問題を検出しました。Gmail で通知します...")
        try:
            from notifier import send_notification

            body = report + (
                "\n\n"
                "【対処方法】\n"
                "  1. update_token.ps1 を実行してください\n"
                "  2. Google トークンが invalid_grant の場合は再認証が必要です：\n"
                "     cd project_ai_academy\n"
                "     python -c \"import gspread; gspread.oauth()\"\n"
                "  3. 次回 Phase A（JST 17:00）までに更新してください\n"
            )
            send_notification("[警告] Soul Reboot - トークン期限切れ検知", body)
        except Exception as e:
            print(f"[NOTIFY] 通知送信失敗: {e}")

        sys.exit(1)

    print("\n全トークン正常。Phase A を安全に実行できます。")


if __name__ == "__main__":
    main()

"""
notifier.py
Soul Reboot - Gmail通知モジュール

環境変数:
    GMAIL_ADDRESS       : 送信元・送信先のGmailアドレス
    GMAIL_APP_PASSWORD  : Googleアカウントのアプリパスワード（16文字）

設定されていない場合は通知をスキップし、警告のみ表示する。

アプリパスワードの取得方法:
    1. Googleアカウント → セキュリティ → 2段階認証を有効化
    2. 「アプリパスワード」を検索 → 新しいパスワードを生成（16文字）
    3. 環境変数 GMAIL_APP_PASSWORD にその値を設定
"""

import os
import smtplib
from email.mime.text import MIMEText


def _get_credentials() -> tuple[str, str] | None:
    """環境変数からGmail認証情報を取得。未設定の場合はNoneを返す"""
    address = os.environ.get("GMAIL_ADDRESS", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not address or not password:
        return None
    return address, password


def send_notification(subject: str, body: str) -> bool:
    """
    Gmailでメールを送信する（自分宛）。
    成功したらTrue、スキップ・失敗したらFalseを返す。
    """
    creds = _get_credentials()
    if creds is None:
        print("  [NOTIFY] スキップ: GMAIL_ADDRESS / GMAIL_APP_PASSWORD が未設定")
        return False

    address, password = creds

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = address

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(address, password)
            smtp.send_message(msg)
        print(f"  [NOTIFY] 送信完了: {subject}")
        return True
    except Exception as e:
        print(f"  [NOTIFY] 送信エラー: {e}")
        return False


def notify_success(
    episode_number: int,
    title: str,
    cliffhanger: str,
    elapsed_seconds: float = 0,
    script_char_count: int = 0,
) -> None:
    """作業完了通知"""
    # 作業時間のフォーマット
    mins, secs = divmod(int(elapsed_seconds), 60)
    elapsed_str = f"{mins}分{secs}秒"

    # 動画時間の概算（日本語TTS: 約4文字/秒）
    estimated_sec = script_char_count / 4 if script_char_count > 0 else 0
    estimated_min = estimated_sec / 60
    video_duration_str = f"約{estimated_min:.0f}分" if estimated_min > 0 else "---"

    subject = f"[完了] Soul Reboot 第{episode_number}話 生成完了"
    body = f"""第{episode_number}話 生成完了

タイトル: {title}
クリフハンガー: {cliffhanger}

作業時間: {elapsed_str}
台本文字数: {script_char_count:,}文字
動画時間（概算）: {video_duration_str}

【確認作業】
□ Episodes - タイトル確認・修正
□ Scripts  - 台本確認（approved=TRUE）
□ Comments - コメント調整
□ Assets   - 画像/音声 承認
"""
    send_notification(subject, body)


def notify_error(episode_number: int, step: str, error: Exception) -> None:
    """エラー通知"""
    subject = f"[エラー] Soul Reboot 第{episode_number}話 エラー発生"
    body = f"""第{episode_number}話 エラー停止

ステップ: {step}
エラー: {type(error).__name__}: {error}

→ PC側でログを確認してください
"""
    send_notification(subject, body)


def notify_youtube_uploaded(episode_number: int, title: str, youtube_url: str) -> None:
    """YouTubeアップロード完了通知"""
    subject = f"[公開] Soul Reboot 第{episode_number}話 YouTube公開完了"
    body = f"""第{episode_number}話 YouTube公開完了

タイトル: {title}
URL: {youtube_url}

→ コメント欄をチェックしてください
"""
    send_notification(subject, body)

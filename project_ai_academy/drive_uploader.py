"""
drive_uploader.py
Soul Reboot - Google Drive 動画アップローダー

Phase B 完了後に生成した MP4 を指定フォルダへ保存する。

前提条件:
    1. drive_token.json（OAuth2トークン）が配置済み
    2. 環境変数 SOUL_REBOOT_DRIVE_FOLDER_ID に保存先フォルダIDを設定

ローカルでの初回認証:
    py drive_uploader.py --auth
"""

import argparse
import os
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from drive_auth import get_drive_client


class DriveUploader:
    """Google Drive API v3 による動画アップローダー"""

    def __init__(self):
        self.drive = get_drive_client()

    def upload(self, file_path: str, ep_num: int, title: str, folder_id: str = "") -> str:
        """動画ファイルをGoogle Driveにアップロードし、共有リンクを返す。

        Args:
            file_path: アップロードする動画ファイルのパス
            ep_num: 話数（ファイル名に使用）
            title: エピソードタイトル
            folder_id: 保存先Google DriveフォルダID（省略時はマイドライブ直下）

        Returns:
            Drive上のファイルURL（共有リンク）
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {file_path}")

        file_name = f"ep{ep_num:03d}_{title}.mp4"

        file_metadata: dict = {"name": file_name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaFileUpload(
            file_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        print(f"[DRIVE] アップロード開始: {file_name}")

        request = self.drive.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink",
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"  アップロード中... {int(status.progress() * 100)}%")

        file_id = response["id"]
        link = response.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
        print(f"[DRIVE] 完了: {link}")
        return link


def main():
    parser = argparse.ArgumentParser(description="Google Drive 認証トークン生成")
    parser.add_argument("--auth", action="store_true", help="ブラウザ認証を実行してトークンを生成する")
    args = parser.parse_args()

    if args.auth:
        get_drive_client()
        print("drive_token.json を生成しました。")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

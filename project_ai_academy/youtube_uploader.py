"""
youtube_uploader.py
Soul Reboot - YouTube動画アップローダー

YouTube Data API v3 を使用して動画を予約アップロードする。

初回実行時:
    ブラウザが自動で開き、Googleアカウントでの認証が求められる。
    認証完了後、youtube_token.json にトークンがキャッシュされる。

前提条件:
    1. Google Cloud Console で YouTube Data API v3 を有効化済み
    2. credentials.json（OAuth 2.0 Desktop Client）が同ディレクトリに配置済み

実行コマンド:
    py youtube_uploader.py --video videos/ep001.mp4 --title "第1話 タイトル" --description "説明文"
    py youtube_uploader.py --video videos/ep001.mp4 --title "タイトル" --publish-at "2026-03-13T06:00:00+09:00"
"""

import argparse
import os
from datetime import datetime, timedelta, timezone

from googleapiclient.http import MediaFileUpload

from youtube_auth import get_youtube_client


# デフォルト設定
DEFAULT_CATEGORY_ID = "24"  # Entertainment
DEFAULT_TAGS = ["Soul Reboot", "ソウルリブート", "アニメ", "AI生成", "連載", "物語"]

# 日本時間
JST = timezone(timedelta(hours=9))


class YouTubeUploader:
    """YouTube Data API v3 による動画アップローダー"""

    def __init__(self):
        self.youtube = get_youtube_client()

    def upload(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        publish_at: str | None = None,
        category_id: str = DEFAULT_CATEGORY_ID,
    ) -> tuple[str, str]:
        """動画をYouTubeにアップロードする。

        Args:
            video_path: 動画ファイルのパス
            title: 動画タイトル
            description: 動画の説明文
            tags: タグリスト（省略時はデフォルトタグ）
            publish_at: 予約公開日時（ISO 8601形式、省略時は即時公開）
            category_id: YouTubeカテゴリID

        Returns:
            (video_id, youtube_url) のタプル
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

        if tags is None:
            tags = DEFAULT_TAGS.copy()

        # プライバシー設定（常に非公開でアップロード）
        privacy_status = "private"

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category_id,
                "defaultLanguage": "ja",
                "defaultAudioLanguage": "ja",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        # publish_at は無視し、常に非公開のままアップロード
        # 公開は手動で行う

        # Resumable upload
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        print(f"[UPLOAD] アップロード開始: {video_path}")
        print(f"  タイトル: {title}")
        print(f"  公開設定: {privacy_status}")
        if publish_at:
            print(f"  予約公開: {publish_at}")

        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"  アップロード中... {progress}%")

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"[UPLOAD] 完了: {video_url}")

        return video_id, video_url

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """カスタムサムネイルを設定する（将来用）"""
        if not os.path.exists(thumbnail_path):
            print(f"  WARN: サムネイルが見つかりません: {thumbnail_path}")
            return False

        media = MediaFileUpload(thumbnail_path, mimetype="image/png")
        self.youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
        print(f"  サムネイル設定完了: {thumbnail_path}")
        return True


def get_next_publish_time() -> str:
    """翌朝06:00 JSTのISO 8601文字列を返す"""
    now = datetime.now(JST)
    tomorrow_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now.hour >= 6:
        tomorrow_6am += timedelta(days=1)
    return tomorrow_6am.isoformat()


def main():
    parser = argparse.ArgumentParser(description="Soul Reboot YouTube アップローダー")
    parser.add_argument("--video", required=True, help="動画ファイルのパス")
    parser.add_argument("--title", required=True, help="動画タイトル")
    parser.add_argument("--description", default="", help="動画の説明文")
    parser.add_argument(
        "--publish-at",
        default=None,
        help="予約公開日時（ISO 8601形式）。省略時は即時公開",
    )
    parser.add_argument(
        "--schedule-tomorrow",
        action="store_true",
        help="翌朝06:00 JSTに予約公開する",
    )
    args = parser.parse_args()

    publish_at = args.publish_at
    if args.schedule_tomorrow:
        publish_at = get_next_publish_time()
        print(f"[SCHEDULE] 予約公開: {publish_at}")

    uploader = YouTubeUploader()
    video_id, url = uploader.upload(
        video_path=args.video,
        title=args.title,
        description=args.description,
        publish_at=publish_at,
    )
    print(f"\nDONE: {url} (video_id: {video_id})")


if __name__ == "__main__":
    main()

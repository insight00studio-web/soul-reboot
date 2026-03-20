"""
youtube_analytics.py
Soul Reboot - YouTube視聴データ・コメント自動収集

YouTube Data API v3 を使用して以下を収集する:
    1. 動画統計（視聴回数・いいね数・コメント数）
    2. コメントスレッド（最新コメント）
    3. チャンネル統計（登録者数・総再生回数）

コメント感情分析は Claude Opus を使用。

前提条件:
    1. youtube_token.json に youtube.readonly + youtube.force-ssl スコープが含まれていること
    2. credentials.json（OAuth 2.0 Desktop Client）が同ディレクトリに配置済み
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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


class YouTubeAnalytics:
    """YouTube Data API v3 による視聴データ・コメント収集"""

    def __init__(self):
        self.youtube = self._authenticate()

    def _authenticate(self):
        """OAuth2認証を行い、YouTube APIクライアントを返す"""
        creds = None

        if YOUTUBE_TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(
                str(YOUTUBE_TOKEN_FILE), SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("[ANALYTICS AUTH] トークンをリフレッシュ中...")
                creds.refresh(Request())
            else:
                if not CREDENTIALS_FILE.exists():
                    print(f"ERROR: {CREDENTIALS_FILE} が見つかりません")
                    sys.exit(1)
                print("[ANALYTICS AUTH] ブラウザで認証してください...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(YOUTUBE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            print("[ANALYTICS AUTH] 認証成功。トークンを保存しました。")

        return build("youtube", "v3", credentials=creds)

    def get_video_stats(self, video_ids: list[str]) -> list[dict]:
        """
        videos.list(part="statistics") で動画統計を一括取得。
        最大50件を1リクエストで処理（APIクォータ: 1ユニット）。

        Returns:
            [{"video_id": "xxx", "views": 123, "likes": 10, "comments": 5}, ...]
        """
        if not video_ids:
            return []

        results = []
        # 50件ずつバッチ処理
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                response = self.youtube.videos().list(
                    part="statistics",
                    id=",".join(batch),
                ).execute()

                for item in response.get("items", []):
                    stats = item.get("statistics", {})
                    results.append({
                        "video_id": item["id"],
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)),
                        "comments": int(stats.get("commentCount", 0)),
                    })
            except HttpError as e:
                print(f"  [WARN] YouTube API error (videos.list): {e}")

        return results

    def get_comments(self, video_id: str, max_results: int = 50) -> list[dict]:
        """
        commentThreads.list で最新コメントを取得。
        APIクォータ: 1ユニット/呼び出し。

        Returns:
            [{"comment_id": "xxx", "author": "name", "text": "...",
              "like_count": 5, "published_at": "2026-03-20T..."}, ...]
        """
        try:
            response = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=max_results,
                order="relevance",
                textFormat="plainText",
            ).execute()

            comments = []
            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "comment_id": item["snippet"]["topLevelComment"]["id"],
                    "author": snippet.get("authorDisplayName", ""),
                    "text": snippet.get("textDisplay", ""),
                    "like_count": int(snippet.get("likeCount", 0)),
                    "published_at": snippet.get("publishedAt", ""),
                })
            return comments

        except HttpError as e:
            error_reason = ""
            if hasattr(e, "error_details") and e.error_details:
                error_reason = str(e.error_details)
            # コメント無効の動画は空リストを返す
            if "commentsDisabled" in str(e) or "forbidden" in str(e).lower():
                print(f"  [INFO] 動画 {video_id} のコメントは無効です")
                return []
            print(f"  [WARN] YouTube API error (commentThreads): {e}")
            return []

    def get_channel_stats(self) -> dict:
        """
        channels.list(mine=True) でチャンネル全体の統計を取得。

        Returns:
            {"subscribers": 123, "total_views": 45678, "video_count": 10}
        """
        try:
            response = self.youtube.channels().list(
                part="statistics",
                mine=True,
            ).execute()

            items = response.get("items", [])
            if not items:
                return {"subscribers": 0, "total_views": 0, "video_count": 0}

            stats = items[0].get("statistics", {})
            return {
                "subscribers": int(stats.get("subscriberCount", 0)),
                "total_views": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
            }
        except HttpError as e:
            print(f"  [WARN] YouTube API error (channels.list): {e}")
            return {"subscribers": 0, "total_views": 0, "video_count": 0}


# ===================================================================
# コメント感情分析（Claude Opus）
# ===================================================================

def analyze_comments_sentiment(comments: list[dict]) -> list[dict]:
    """
    Claude Opus でコメントの感情分析・採用スコアリングを行う。
    autonomous_engine.py の call_opus() と同じCLI経由で呼び出す。

    Input:  [{"comment_id", "author", "text", "like_count", ...}, ...]
    Output: 元のdictに以下を追加して返す:
        - ai_sentiment: 応援 / 批判 / 考察 / リクエスト / その他
        - adoption_score: 0-100（物語への採用適性スコア）
        - summary: 1行要約
    """
    if not comments:
        return []

    # コメントテキストをバッチ化
    comment_texts = []
    for i, c in enumerate(comments):
        comment_texts.append(
            f"[{i}] (いいね:{c.get('like_count', 0)}) {c.get('text', '')[:200]}"
        )

    prompt = f"""あなたはYouTubeアニメチャンネル「Soul Reboot」のコメント分析AIです。
以下のコメントを分析し、JSON配列で結果を返してください。

## チャンネル概要
「Soul Reboot - 100日後の君へ -」は、AIと人間の100日間を描く連載アニメです。
主人公シンジ（人間）とヒロインのナギサ（AI）の物語で、視聴者コメントが物語展開に影響を与えます。

## 分析基準
- **ai_sentiment**: 以下から1つ選択
  - 応援: キャラクターや物語への応援・好意
  - 批判: ストーリーや演出への不満・改善要望
  - 考察: 伏線や今後の展開についての推理・分析
  - リクエスト: 特定の展開やキャラクター行動の要望
  - その他: 上記に当てはまらない
- **adoption_score**: 0-100（物語に採用した場合の面白さ・有用性）
  - 考察コメント: 的確な伏線指摘は高スコア（60-100）
  - リクエスト: 物語を豊かにする要望は高スコア（40-80）
  - 応援: キャラへの具体的言及あり（30-60）
  - いいね数が多いコメントは +10〜20 のボーナス
- **summary**: コメントの要点を1行で

## コメント一覧
{chr(10).join(comment_texts)}

## 出力フォーマット（JSON配列）
[
  {{"index": 0, "ai_sentiment": "考察", "adoption_score": 75, "summary": "ナギサの記憶消去に関する伏線を指摘"}},
  ...
]
"""

    result = _call_opus_for_analysis(prompt)

    # 結果をコメントにマージ
    if isinstance(result, list):
        for item in result:
            idx = item.get("index", -1)
            if 0 <= idx < len(comments):
                comments[idx]["ai_sentiment"] = item.get("ai_sentiment", "その他")
                comments[idx]["adoption_score"] = item.get("adoption_score", 0)
                comments[idx]["summary"] = item.get("summary", "")
    else:
        print(f"  [WARN] コメント分析結果のパースに失敗: {str(result)[:200]}")
        # フォールバック: 全コメントにデフォルト値を設定
        for c in comments:
            c.setdefault("ai_sentiment", "その他")
            c.setdefault("adoption_score", 0)
            c.setdefault("summary", "")

    return comments


def _call_opus_for_analysis(prompt: str, timeout: int = 300) -> list | str:
    """Claude Code CLI経由でOpus 4.6を呼び出す（感情分析用）"""
    cmd = ["claude", "-p", "--output-format", "text", "--model", "claude-opus-4-6"]

    # CLAUDECODE環境変数を除去（ネスト防止）
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    print("  [OPUS] コメント感情分析中...")
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            env=env,
        )

        if result.returncode != 0:
            print(f"  [WARN] Claude CLI error: {result.stderr[:200]}")
            return []

        raw = result.stdout.strip()
        print(f"  [OPUS] 感情分析完了: {len(raw)}文字")

        # JSONブロック抽出
        json_match = re.search(r'```json\s*([\s\S]*?)```', raw)
        if json_match:
            raw = json_match.group(1).strip()

        # 末尾カンマ除去してパース
        cleaned = re.sub(r',\s*([\]}])', r'\1', raw)
        return json.loads(cleaned)

    except subprocess.TimeoutExpired:
        print("  [WARN] コメント分析がタイムアウトしました")
        return []
    except json.JSONDecodeError:
        print(f"  [WARN] コメント分析結果のJSONパースに失敗")
        return []
    except Exception as e:
        print(f"  [WARN] コメント分析エラー: {e}")
        return []


# ===================================================================
# ユーティリティ
# ===================================================================

def extract_video_id(youtube_url: str) -> str | None:
    """YouTube URLからvideo_idを抽出する"""
    if not youtube_url:
        return None
    # https://youtu.be/VIDEO_ID
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', youtube_url)
    if match:
        return match.group(1)
    # https://www.youtube.com/watch?v=VIDEO_ID
    match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', youtube_url)
    if match:
        return match.group(1)
    # https://studio.youtube.com/video/VIDEO_ID/...
    match = re.search(r'youtube\.com/video/([a-zA-Z0-9_-]{11})', youtube_url)
    if match:
        return match.group(1)
    return None


# ===================================================================
# テスト用エントリポイント
# ===================================================================

if __name__ == "__main__":
    print("YouTube Analytics - テスト実行")
    print("=" * 50)

    yt = YouTubeAnalytics()

    # チャンネル統計
    channel = yt.get_channel_stats()
    print(f"\nチャンネル統計:")
    print(f"  登録者: {channel['subscribers']}")
    print(f"  総再生: {channel['total_views']}")
    print(f"  動画数: {channel['video_count']}")

    # テスト用: video_idが引数で渡された場合
    if len(sys.argv) > 1:
        video_id = sys.argv[1]
        print(f"\n動画統計 ({video_id}):")
        stats = yt.get_video_stats([video_id])
        for s in stats:
            print(f"  視聴: {s['views']} / いいね: {s['likes']} / コメント: {s['comments']}")

        print(f"\nコメント取得中...")
        comments = yt.get_comments(video_id, max_results=10)
        print(f"  {len(comments)}件取得")

        if comments:
            print(f"\n感情分析中...")
            analyzed = analyze_comments_sentiment(comments)
            for c in analyzed:
                print(f"  [{c.get('ai_sentiment', '?')}] (スコア:{c.get('adoption_score', 0)}) {c.get('text', '')[:50]}")

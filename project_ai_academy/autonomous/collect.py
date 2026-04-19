"""autonomous/collect.py - Phase A の収集ステップ。

step_collect_news:      Gemini Flash でニュースを取得し News シートに書き込む
step_collect_analytics: YouTube Data API で直近話の視聴データ・コメントを収集
step_score_comments:    Comments シートから上位 N 件を ADOPTED にマーク
"""

from datetime import date

from sheets_db import SoulRebootDB
from llm_client import call_gemini
from utils import safe_int
from youtube_analytics import YouTubeAnalytics, analyze_comments_sentiment


def step_collect_news(db: SoulRebootDB, config: dict) -> list[dict]:
    """
    Geminiにその日の注目ニュースを取得させ、Newsシートに書き込む。
    """
    print("\n[NEWS] STEP 1: 今日のリアルニュース収集...")

    today = date.today().isoformat()
    count = int(config.get("NEWS_FETCH_COUNT", 5))

    prompt = f"""
あなたは日本語のニュースリサーチャーです。
今日（{today}）の注目ニュースを{count}件、以下のJSON配列形式で出力してください。

**重要: カテゴリの多様性を確保すること。**
以下のカテゴリから最低3つ以上の異なるカテゴリを含めてください。
AI・テクノロジーは最大2件までとし、残りは別カテゴリから選んでください。

カテゴリ一覧:
1. AI・テクノロジー（最大2件まで）
2. 季節・行事（今の季節に関連する話題、天気、自然現象）
3. 文化・エンタメ（映画、音楽、アニメ、ゲーム、本など）
4. 科学・宇宙（宇宙探査、医療、環境、生物学など）
5. スポーツ（国内外の注目試合、選手の話題）
6. 社会・ほっこり（感動する話題、人間ドラマ、地域の話題）
7. 国際（海外の興味深い出来事、文化の違い）

※ 政治・宗教・犯罪・災害（地震速報等は除く）・センシティブな話題は避けてください。

出力フォーマット:
[
  {{
    "headline": "ニュースの見出し（30字以内）",
    "source": "情報ソース名（例: NHK, TechCrunch JP）",
    "category": "上記カテゴリ名のどれか",
    "story_hook": "この話題をAI×青春物語にどう活かせるか（1文）",
    "relevance_score": 80
  }}
]

relevance_scoreは「AIと記憶をテーマにした青春物語」への関連度（0〜100）です。
"""
    try:
        news_items = call_gemini(prompt, model_name="gemini-3-flash-preview", response_format="json")
        if isinstance(news_items, list):
            mapped_news = []
            for n in news_items:
                mapped_news.append({
                    "見出し": n.get("headline", ""),
                    "情報ソース": n.get("source", ""),
                    "カテゴリ": n.get("category", ""),
                    "関連スコア": n.get("relevance_score", 0),
                    "活用ヒント": n.get("story_hook", ""),
                })
            db.append_news(mapped_news)
            print(f"  → {len(news_items)}件のニュースを収集・記録しました")
            return mapped_news
    except Exception as e:
        print(f"  ERROR: ニュース収集エラー: {e}")

    return []


def step_collect_analytics(db: SoulRebootDB, config: dict) -> dict:
    """
    YouTube Data API v3 で直近エピソードの視聴データ・コメントを収集し、
    スプレッドシートに書き込む。
    YouTube URLがまだない場合（初期エピソード）はスキップ。
    """
    print("\n[ANALYTICS] STEP 1.5: YouTube視聴データ・コメント収集...")

    fetch_limit = safe_int(config.get("ANALYTICS_FETCH_EPISODES", 3), 3)
    recent_episodes = db.get_video_ids_for_recent_episodes(limit=fetch_limit)

    if not recent_episodes:
        print("  → YouTube公開済みエピソードなし。スキップします。")
        return {"episodes_fetched": 0, "comments_collected": 0}

    print(f"  → 対象エピソード: {len(recent_episodes)}話")

    try:
        yt = YouTubeAnalytics()
    except Exception as e:
        print(f"  [WARN] YouTube API認証に失敗: {e}")
        print("  → Analytics収集をスキップします。")
        return {"episodes_fetched": 0, "comments_collected": 0}

    # 動画統計の取得
    video_ids = [ep["video_id"] for ep in recent_episodes]
    stats = yt.get_video_stats(video_ids)
    stats_map = {s["video_id"]: s for s in stats}

    # Analyticsシートに書き込む
    analytics_rows = []
    for ep in recent_episodes:
        vid = ep["video_id"]
        s = stats_map.get(vid, {})
        views = s.get("views", 0)
        likes = s.get("likes", 0)
        comments_count = s.get("comments", 0)
        engagement = round((likes + comments_count) / views * 100, 2) if views > 0 else 0

        # 前日比の計算
        prev_analytics = db.get_latest_analytics(limit=20)
        prev_views = 0
        for pa in prev_analytics:
            if str(pa.get("話数", "")) == str(ep["episode_number"]):
                prev_views = int(pa.get("視聴回数", 0)) if pa.get("視聴回数") else 0
                break

        analytics_rows.append({
            "話数": ep["episode_number"],
            "video_id": vid,
            "視聴回数": views,
            "いいね数": likes,
            "コメント数": comments_count,
            "エンゲージメント率": engagement,
            "前日比_視聴": views - prev_views,
        })
        print(f"  第{ep['episode_number']}話: 視聴{views} / いいね{likes} / コメント{comments_count}")

    if analytics_rows:
        db.append_analytics(analytics_rows)

    # コメント収集と感情分析
    existing_ids = db.get_existing_comment_ids()
    total_new_comments = 0

    for ep in recent_episodes:
        comment_fetch_count = safe_int(config.get("COMMENT_FETCH_COUNT", 50), 50)
        raw_comments = yt.get_comments(ep["video_id"], max_results=comment_fetch_count)
        # 重複除外
        new_comments = [c for c in raw_comments if c.get("comment_id") not in existing_ids]

        if not new_comments:
            continue

        print(f"  第{ep['episode_number']}話: 新規コメント{len(new_comments)}件")

        # Claude Opus で感情分析
        analyzed = analyze_comments_sentiment(new_comments)

        # Commentsシート用にカラム名をマッピング
        sheet_comments = []
        for c in analyzed:
            sheet_comments.append({
                "コメントID": c.get("comment_id", ""),
                "対象話数": ep["episode_number"],
                "投稿者名": c.get("author", ""),
                "コメント本文": c.get("text", ""),
                "いいね数": c.get("like_count", 0),
                "AI感情分析": c.get("ai_sentiment", ""),
                "採用スコア": c.get("adoption_score", 0),
            })

        added = db.append_comments_batch(sheet_comments)
        total_new_comments += added
        existing_ids.update(c.get("comment_id", "") for c in new_comments)

    summary = {
        "episodes_fetched": len(recent_episodes),
        "comments_collected": total_new_comments,
    }
    print(f"  → 収集完了: {summary['episodes_fetched']}話分 / 新規コメント{summary['comments_collected']}件")
    return summary


def step_score_comments(db: SoulRebootDB) -> list[dict]:
    """
    Commentsシートの未処理コメントから採用スコアの高い上位3件を選択し、
    ADOPTEDにマークして返す。
    """
    print("\n[COMMENTS] STEP 2: コメントスコアリング...")

    top_comments = db.get_top_pending_comments(limit=3)
    if top_comments:
        print(f"  → 採用候補コメント: {len(top_comments)}件")
        # 採用コメントをADOPTEDにマーク
        adopted_ids = [str(c.get("コメントID", "")) for c in top_comments if c.get("コメントID")]
        if adopted_ids:
            db.mark_comments_adopted(adopted_ids)
    else:
        print("  → 採用候補コメントなし（初回または未収集）")

    return top_comments

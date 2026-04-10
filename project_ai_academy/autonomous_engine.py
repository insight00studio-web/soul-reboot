"""
autonomous_engine.py
Soul Reboot - 24時間自律生成エンジン（メインエントリポイント）

実行コマンド:
    python autonomous_engine.py
    python autonomous_engine.py --episode 5  （特定話数を指定して実行）

処理フロー:
    ① Config読み込み
    ② ニュース収集（Gemini Flash） → Newsシート
    ③ コメント収集・スコアリング → Commentsシート
    ④ L2記憶 + 未回収伏線 + 採用コメント → Architectプロンプト構築
    ⑤ Architect（Opus 4.6）がプロットを生成 → Episodesシート
    ⑥ Writer（Gemini Pro）が台本を生成 → Scriptsシート
    ⑦ Editor（Opus 4.6）が台本を監修・編集 → Scriptsシート上書き
    ⑧ 伏線をForeshadowingシートに記録
    ⑨ Parametersシートを更新
    ⑩ Memory_L2シートを更新
    ⑪ Configの CURRENT_EPISODE を +1
    ⑫ 終了レポート出力
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

from sheets_db import SoulRebootDB
from notifier import notify_success, notify_error
from youtube_analytics import YouTubeAnalytics, analyze_comments_sentiment
from llm_client import call_gemini, call_opus, parse_json_robust
from utils import safe_int
from event_calendar import get_event_on_date

# .envファイルから環境変数を読み込む（プロジェクトルートにある場合）
load_dotenv()

# ===================================================================
# 設定
# ===================================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")


# ===================================================================
# ヘルパー関数
# ===================================================================

def load_prompt(filename: str) -> str:
    """promptsフォルダからMarkdownファイルを読み込む"""
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _safe_encode(text: str, length: int = 9999) -> str:
    """cp932等のターミナルで表示できない文字をエスケープする"""
    return text[:length].encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")


_STORY_START = date(2026, 4, 8)  # Day 1 = 入学式

_NATIONAL_HOLIDAYS = {
    date(2026, 4, 29),  # 昭和の日
    date(2026, 5, 3),   # 憲法記念日
    date(2026, 5, 4),   # みどりの日
    date(2026, 5, 5),   # こどもの日
    date(2026, 5, 6),   # 振替休日
}

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]


def _get_story_date_info(episode_number: int) -> dict:
    """物語内日付・曜日・服装を計算する"""
    story_date = _STORY_START + timedelta(days=episode_number - 1)
    weekday = _WEEKDAYS_JA[story_date.weekday()]
    is_holiday = story_date in _NATIONAL_HOLIDAYS
    is_weekend = story_date.weekday() >= 5
    is_school_day = not is_holiday and not is_weekend

    if is_holiday:
        day_type = "祝日（学校なし）"
    elif is_weekend:
        day_type = "休日（学校なし）"
    else:
        day_type = "平日（授業あり）"

    costume = "制服" if is_school_day else "私服"
    return {
        "story_date": story_date.strftime("%m月%d日"),
        "weekday": weekday,
        "day_type": day_type,
        "costume": costume,
        "is_school_day": is_school_day,
    }


def _summarize_scene_plan(scene_plan: list) -> str:
    """scene_planからメイン舞台のサマリー文字列を生成する（シート保存用）"""
    if not scene_plan:
        return ""
    locations = [s.get("location", "") for s in scene_plan if s.get("location")]
    unique = list(dict.fromkeys(locations))  # 順序を保ちつつ重複除去
    if not unique:
        return ""
    if len(unique) == 1:
        return f"{unique[0]}（単一舞台）"
    return "→".join(unique)

# ===================================================================
# STEP 1: ニュース収集
# ===================================================================

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


# ===================================================================
# STEP 1.5: YouTube Analytics 収集
# ===================================================================

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


# ===================================================================
# STEP 2: コメントスコアリング
# ===================================================================

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


# ===================================================================
# STEP 3: Architect - プロット生成
# ===================================================================

def _build_architect_prompt(db: SoulRebootDB, config: dict,
                             episode_number: int, news: list[dict],
                             top_comments: list[dict],
                             quality_feedback: str = "",
                             publish_date: date | None = None,
                             event_name: str | None = None,
                             story_date_info: dict | None = None) -> str:
    """Architectに渡すプロンプト文字列を構築する"""
    architect_base = load_prompt("architect_prompt.md")
    l1_context = db.build_l1_context()
    foreshadowing_context = db.build_open_foreshadowing_context()
    past_cliffhangers = db.build_past_cliffhangers_context()
    story_progress = db.build_story_progress_context()
    analytics_context = db.build_analytics_context()
    past_structures = db.build_past_structures_context()
    past_scene_settings = db.build_past_scene_settings_context()
    dialogue_samples = db.build_dialogue_samples_context()

    # ニュースサマリー
    news_context = "今日のニュース（参考 — 多様なジャンルから物語のスパイスとして活用してください）:\n"
    for n in news[:5]:
        hook = n.get('活用ヒント', '')
        hook_str = f" → {hook}" if hook else ""
        news_context += f"  - [{n.get('カテゴリ')}] {n.get('見出し')}{hook_str}\n"

    # コメントサマリー
    comment_context = "採用候補コメント（参考）:\n"
    if top_comments:
        for c in top_comments:
            comment_context += f"  - 「{c.get('コメント本文', '')[:50]}」（スコア:{c.get('採用スコア')}）\n"
    else:
        comment_context += "  （なし）\n"

    # パラメータ
    params = db.get_latest_parameters()
    param_context = (
        f"現在のパラメータ: 信頼度:{params.get('信頼度',20)} / "
        f"覚醒度:{params.get('覚醒度',0)} / 記録度:{params.get('記録度',5)}"
    )

    # パラメータ目標レンジ
    targets = db.get_parameter_targets(episode_number)
    target_context = (
        f"パラメータ目標レンジ（ロードマップ準拠）: "
        f"信頼度:{targets['trust'][0]}〜{targets['trust'][1]} / "
        f"覚醒度:{targets['awakening'][0]}〜{targets['awakening'][1]}"
    )

    today = date.today().isoformat()
    pub_date_str = publish_date.isoformat() if publish_date else today

    event_section = f"""
---
## 公開日イベント（重要）

公開日（{pub_date_str}）は「**{event_name}**」です。
物語の流れを壊さず、キャラクターたちがこのイベントを自然に認識・体験する形で台本に織り込んでください。
強引にイベントを前面に出す必要はありませんが、雰囲気・セリフ・小道具などに反映させてください。
""" if event_name else ""

    feedback_section = f"""
---
## 品質フィードバック（前回のEditor評価）

前回の台本が品質基準を満たしませんでした。以下の問題点を必ず解消したプロットを生成してください:
{quality_feedback}
""" if quality_feedback else ""

    sd = story_date_info or {}
    story_date_line = (
        f"- **物語内日付**: {sd.get('story_date', '不明')}（{sd.get('weekday', '?')}曜日 / {sd.get('day_type', '?')}）\n"
        f"- **服装**: {sd.get('costume', '制服')}（Writer・Architectはこれに従うこと）"
    ) if sd else ""

    return f"""
{architect_base}

---
## 今回の生成情報

- **台本生成日**: {today}
- **公開予定日**: {pub_date_str}{"（" + event_name + "）" if event_name else ""}
- **エピソード番号**: 第{episode_number}話
- **フェーズ**: {config.get('PHASE', 'PHASE_1')}
{story_date_line}

{param_context}
{target_context}

{l1_context}

{foreshadowing_context}

{past_cliffhangers}

{story_progress}

{past_structures}

{past_scene_settings}

{dialogue_samples}

{news_context}

{comment_context}

{analytics_context}
{event_section}
{feedback_section}
---
## 出力フォーマット（JSON形式で出力してください）

{{
  "episode_number": {episode_number},
  "title": "タイトル",
  "main_objective": "この話で達成すること",
  "emotional_curve": "例: 30→60→90",
  "structure_type": "日常→異変→発見（使用済みリストにない型を選択）",
  "comedy_pattern": "A: 字義解釈型（直近3話と異なるパターンを選択）",
  "shinji_agency": "シンジが主体的に行う行動（受け身のみなら空文字）",
  "plot_summary": {{
    "introduction": "導入（3〜4文）",
    "development": "展開（3〜4文）",
    "climax": "クライマックス（3〜4文）"
  }},
  "scene_plan": [
    {{"scene_label": "導入", "location": "場所（例: 体育館）", "time": "時間帯（例: 5限・体育の授業中）", "note": "そのシーンで起こること"}},
    {{"scene_label": "展開", "location": "場所", "time": "時間帯", "note": "そのシーンで起こること"}},
    {{"scene_label": "クライマックス", "location": "場所", "time": "時間帯", "note": "そのシーンで起こること"}}
  ],
  "foreshadowing_added": [
    {{"description": "追加する伏線（最大1件。不要なら空配列[]）", "target_episode": 10, "importance": "MID"}}
  ],
  "foreshadowing_resolved": [
    {{"id": "FS-001", "resolution_note": "どう回収したか"}}
  ],
  "cliffhanger": "次話への引き",
  "parameter_delta": {{
    "trust_delta": 0,
    "awakening_delta": 0,
    "record_delta": 0,
    "trigger_event": "変動理由"
  }},
  "adopted_comment_note": "採用したコメントがあれば説明"
}}
"""


def step_architect(db: SoulRebootDB, config: dict,
                   episode_number: int, news: list[dict],
                   top_comments: list[dict],
                   quality_feedback: str = "") -> dict:
    """
    ArchitectプロンプトにL2記憶・伏線・ニュース・コメントを注入し、
    Opusにプロットを生成させ、Episodesシートに書き込む。
    """
    print(f"\n[ARCHITECT] STEP 3: Architect - 第{episode_number}話プロット生成...")

    # 公開予定日の計算（エピソード番号から確定的に算出 = 生成タイミングに依存しない）
    publish_date = _STORY_START + timedelta(days=episode_number - 1)
    event_name = get_event_on_date(publish_date)
    if event_name:
        print(f"  [ARCHITECT] 公開日イベント検知: {publish_date} = {event_name}")

    story_date_info = _get_story_date_info(episode_number)
    print(f"  [ARCHITECT] 物語内日付: {story_date_info['story_date']}（{story_date_info['weekday']}曜日）服装: {story_date_info['costume']}")

    full_prompt = _build_architect_prompt(
        db, config, episode_number, news, top_comments, quality_feedback,
        publish_date=publish_date, event_name=event_name,
        story_date_info=story_date_info,
    )

    max_json_retries = 2
    for json_attempt in range(max_json_retries + 1):
        plot = call_opus(full_prompt)

        if isinstance(plot, dict):
            break

        # テキストで返ってきた場合、JSON部分の抽出を試みる
        try:
            plot = parse_json_robust(plot)
            break
        except json.JSONDecodeError:
            if json_attempt < max_json_retries:
                print(f"  [ARCHITECT] JSONパース失敗。リトライ {json_attempt + 1}/{max_json_retries}...")
            else:
                raise RuntimeError(f"Architectの応答が{max_json_retries + 1}回連続でJSON不正。手動再実行してください。")

    # Episodesシートに書き込む
    episode_row = {
        "話数": episode_number,
        "公開日": publish_date.isoformat(),
        "物語内の日数": episode_number,
        "フェーズ": config.get("PHASE", "PHASE_1"),
        "タイトル案": plot.get("title", ""),
        "確定タイトル": "",
        "この話の目的": plot.get("main_objective", ""),
        "感情曲線": plot.get("emotional_curve", ""),
        "プロット要約": json.dumps(plot.get("plot_summary", {}), ensure_ascii=False),
        "クリフハンガー": plot.get("cliffhanger", ""),
        "構造パターン": plot.get("structure_type", ""),
        "掛け合いパターン": plot.get("comedy_pattern", ""),
        "シーン舞台": _summarize_scene_plan(plot.get("scene_plan", [])),
        "ステータス": "PLANNED",
        "YouTube_URL": "",
        "メモ": "",
    }
    db.upsert_episode(episode_row)
    print(f"  → タイトル案:「{plot.get('title')}」")

    return plot


# ===================================================================
# STEP 4: Writer - 台本生成
# ===================================================================

def step_writer(db: SoulRebootDB, config: dict, episode_number: int, plot: dict,
                story_date_info: dict | None = None) -> list[dict]:
    """
    Writerプロンプトにプロットを注入し、Geminiに台本を生成させ、
    Scriptsシートに書き込む（approved=FALSE）。
    """
    print(f"\n[WRITER] STEP 4: Writer - 第{episode_number}話台本生成...")

    writer_base = load_prompt("writer_prompt.md")
    plot_json = json.dumps(plot, ensure_ascii=False, indent=2)

    # 服装指定を明示的に注入（Writerへ確実に伝達するため）
    costume_section = ""
    if story_date_info:
        sd = story_date_info
        if sd["costume"] == "私服":
            nagisa_costume = "casual clothes, white blouse"
            shinji_costume = "casual clothes, hoodie"
        else:
            nagisa_costume = "blue school uniform"
            shinji_costume = "dark school uniform"
        costume_section = f"""
---
## 【最重要】服装指定（全シーン必ず統一すること）

物語内日付: **{sd['story_date']}（{sd['weekday']}曜日 / {sd['day_type']}）**
本エピソードの服装: **{sd['costume']}**

全シーンの `image_prompt` で以下の服装を統一して使用すること:
- ナギサ: `{nagisa_costume}`
- シンジ: `{shinji_costume}`

**制服と私服を1エピソード内で混在させることは絶対禁止。**
"""

    full_prompt = f"""
{writer_base}

{costume_section}
---
## 生成するエピソード情報

{plot_json}

---
## 出力フォーマット（JSON配列で出力してください）

各シーンの各発言を1オブジェクトとして出力します:

[
  {{
    "scene_number": 1,
    "scene_name": "シーン名（Architectのscene_planのlocationとtimeを反映。例: 体育館・5限バスケ中 / 屋上・昼休み / スタバ・放課後）",
    "image_prompt": "Stable Diffusion用の英語プロンプト",
    "speaker": "NAGISA | SHINJI | NARRATOR | SYSTEM",
    "line_text": "セリフまたは地の文",
    "tone": "感情トーン（例: 静か, 毒舌, 震え, 叫び, 悲しみ）",
    "audio_file_path": "",
    "approved": "TRUE",
    "notes": ""
  }}
]

必ずシーンは4つ以上、各シーン最低4発言以上（合計20行以上）を含めること。動画尺が約5分になるよう、セリフ・地の文を十分な長さで書くこと。
冒頭は必ず衝撃的なフックから始めること。
"""

    model_name = config.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
    script_lines = call_gemini(full_prompt, model_name=model_name, response_format="json")

    if isinstance(script_lines, list):
        mapped_lines = []
        for line in script_lines:
            mapped_lines.append({
                "シーン番号": line.get("scene_number", ""),
                "シーン名": line.get("scene_name", ""),
                "画像プロンプト": line.get("image_prompt", ""),
                "話者": line.get("speaker", ""),
                "セリフ・地の文": line.get("line_text", ""),
                "感情トーン": line.get("tone", ""),
                "音声キャラ": {"NAGISA": "Despina", "SHINJI": "Orus", "NARRATOR": "Charon", "SYSTEM": "Kore"}.get(line.get("speaker", "").upper(), ""),
                "音声ファイルパス": line.get("audio_file_path", ""),
            })
        db.append_script_lines(episode_number, mapped_lines)
        print(f"  → {len(script_lines)}行の台本を生成・記録しました")
        return mapped_lines
    else:
        print("  WARN: 台本生成に失敗しました")
        return []


# ===================================================================
# STEP 4.5: Editor - Opus 4.6 による台本監修・編集
# ===================================================================

def step_editor(db: SoulRebootDB, episode_number: int,
                plot: dict, script_lines: list[dict]) -> tuple[list[dict], dict]:
    """
    Opus 4.6がWriter（Gemini）の台本を監修・編集し、
    修正版でスプレッドシートを上書きする。
    品質スコアも返す（Quality Gate用）。
    """
    print(f"\n[EDITOR] STEP 4.5: Opus 4.6 - 第{episode_number}話台本監修...")

    editor_base = load_prompt("editor_prompt.md")
    plot_json = json.dumps(plot, ensure_ascii=False, indent=2)
    script_json = json.dumps(script_lines, ensure_ascii=False, indent=2)

    full_prompt = f"""
{editor_base}

---
## プロット（Architectが設計）

{plot_json}

---
## 現在の台本（Writerが生成）

{script_json}

---
## 出力フォーマット

以下のJSON形式で出力してください。品質スコアと修正後の台本の両方を含めること。
変更がなくても全行を出力してください。

```json
{{
  "quality_score": {{
    "character_consistency": 0,
    "structure_variety": 0,
    "comedy_execution": 0,
    "shinji_agency": 0,
    "parameter_alignment": 0,
    "total": 0,
    "issues": []
  }},
  "edited_script": [
    {{
      "シーン番号": 1,
      "シーン名": "シーン名",
      "画像プロンプト": "英語プロンプト（キャラ名NAGISA/SHINJIを必ず含める、detailed face, clear facial features）",
      "話者": "NAGISA | SHINJI | NARRATOR | SYSTEM",
      "セリフ・地の文": "セリフまたは地の文",
      "感情トーン": "トーン",
      "音声キャラ": "Despina | Orus | Charon | Kore",
      "音声ファイルパス": "",
      "notes": "変更理由（変更した行のみ）"
    }}
  ]
}}
```
"""

    max_json_retries = 2
    for json_attempt in range(max_json_retries + 1):
        edited = call_opus(full_prompt)

        if isinstance(edited, dict) or isinstance(edited, list):
            break

        # テキストで返ってきた場合、JSON部分の抽出を試みる
        try:
            edited = parse_json_robust(edited)
            break
        except json.JSONDecodeError:
            if json_attempt < max_json_retries:
                print(f"  [EDITOR] JSONパース失敗。リトライ {json_attempt + 1}/{max_json_retries}...")
            else:
                print("  WARN: Editor応答が{max_json_retries + 1}回連続でJSON不正（元の台本を維持）")
                return script_lines, {"total": 0, "issues": ["Editor応答パースエラー（リトライ超過）"]}

    # 新フォーマット（quality_score + edited_script）のパース
    quality_score = {}
    if isinstance(edited, dict) and "edited_script" in edited:
        quality_score = edited.get("quality_score", {})
        edited_lines = edited.get("edited_script", [])
    elif isinstance(edited, list):
        # 旧フォーマット互換（配列のみ返ってきた場合）
        edited_lines = edited
        quality_score = {"total": 999, "issues": []}
    else:
        print("  WARN: Editor応答が不正（元の台本を維持）")
        return script_lines, {"total": 0, "issues": ["Editor応答パースエラー"]}

    if not isinstance(edited_lines, list) or len(edited_lines) == 0:
        print("  WARN: Editor応答の台本が空（元の台本を維持）")
        return script_lines, {"total": 0, "issues": ["台本が空"]}

    # 変更箇所のサマリーを表示
    changed_count = sum(1 for line in edited_lines if line.get("notes", ""))
    total_score = safe_int(quality_score.get("total"), 0)
    issues = quality_score.get("issues", [])
    print(f"  → {len(edited_lines)}行中 {changed_count}行を修正")
    print(f"  → 品質スコア: {total_score}/500")
    if issues:
        for issue in issues:
            print(f"    - {issue}")

    # スプレッドシートを上書き
    db.replace_script_lines(episode_number, edited_lines)
    print(f"  → スプレッドシート更新完了")

    return edited_lines, quality_score


# ===================================================================
# 視聴者フィードバック → パラメータ微調整
# ===================================================================

def _calculate_viewer_delta(db: SoulRebootDB) -> dict | None:
    """
    直近のアナリティクスとコメント傾向からパラメータ微調整値を計算する。
    各パラメータの調整幅は ±3 以内（Architectの判断が主、視聴者は補助）。
    """
    analytics = db.get_latest_analytics(limit=1)
    if not analytics:
        return None

    latest = analytics[0]
    engagement = float(latest.get("エンゲージメント率", 0)) if latest.get("エンゲージメント率") else 0

    # コメント感情の集計（直近50件）
    recent_sentiments = db.get_recent_sentiments(limit=50)

    if not recent_sentiments:
        # エンゲージメントのみで判断
        if engagement >= 10:
            return {"trust": 0, "awakening": 0, "record": 1, "reason": f"高エンゲージメント{engagement:.1f}%"}
        return None

    counts = Counter(recent_sentiments)
    total = sum(counts.values())

    support_ratio = counts.get("応援", 0) / total  # 応援率
    criticism_ratio = counts.get("批判", 0) / total  # 批判率
    theory_ratio = counts.get("考察", 0) / total  # 考察率

    trust_delta = 0
    awakening_delta = 0
    record_delta = 0
    reasons = []

    # 高エンゲージメント → 記録度 +1〜2
    if engagement >= 10:
        record_delta += 2
        reasons.append(f"エンゲージメント{engagement:.1f}%")
    elif engagement >= 5:
        record_delta += 1

    # 応援多い → 信頼度 +1〜2
    if support_ratio >= 0.5:
        trust_delta += 2
        reasons.append(f"応援{support_ratio*100:.0f}%")
    elif support_ratio >= 0.3:
        trust_delta += 1

    # 批判多い → 覚醒度 +1〜2（緊張感の反映）
    if criticism_ratio >= 0.3:
        awakening_delta += 2
        reasons.append(f"批判{criticism_ratio*100:.0f}%")
    elif criticism_ratio >= 0.15:
        awakening_delta += 1

    # 考察多い → 覚醒度 +1（物語への深い関与）
    if theory_ratio >= 0.3:
        awakening_delta += 1
        reasons.append(f"考察{theory_ratio*100:.0f}%")

    # 上限クリップ（±3）
    trust_delta = max(-3, min(3, trust_delta))
    awakening_delta = max(-3, min(3, awakening_delta))
    record_delta = max(-3, min(3, record_delta))

    if trust_delta == 0 and awakening_delta == 0 and record_delta == 0:
        return None

    return {
        "trust": trust_delta,
        "awakening": awakening_delta,
        "record": record_delta,
        "reason": ", ".join(reasons) if reasons else "視聴者反応",
    }


# ===================================================================
# STEP 5: 伏線・パラメータ・記憶の更新
# ===================================================================

def step_update_metadata(db: SoulRebootDB, episode_number: int, plot: dict) -> None:
    """
    伏線・パラメータ・L2記憶を更新する。
    """
    print(f"\n[SYNC] STEP 5: 伏線・パラメータ・記憶を更新...")

    # 伏線追加
    for fs in plot.get("foreshadowing_added", []):
        db.add_foreshadowing(
            episode_number=episode_number,
            description=fs.get("description", ""),
            target_episode=fs.get("target_episode", episode_number + 10),
            importance=fs.get("importance", "MID"),
        )

    # 伏線回収
    for res in plot.get("foreshadowing_resolved", []):
        db.resolve_foreshadowing(
            foreshadow_id=res.get("id", ""),
            resolved_episode=episode_number,
            resolution_note=res.get("resolution_note", ""),
        )

    # パラメータ更新（Architectの判断 + 視聴者フィードバック微調整）
    prev = db.get_latest_parameters()
    delta = plot.get("parameter_delta", {})
    new_trust = safe_int(prev.get("信頼度"), 20) + safe_int(delta.get("trust_delta"), 0)
    new_awakening = safe_int(prev.get("覚醒度"), 0) + safe_int(delta.get("awakening_delta"), 0)
    new_record = safe_int(prev.get("記録度"), 5) + safe_int(delta.get("record_delta"), 0)

    # 視聴者フィードバックによる微調整（各パラメータ最大±3）
    viewer_delta = _calculate_viewer_delta(db)
    if viewer_delta:
        new_trust += viewer_delta.get("trust", 0)
        new_awakening += viewer_delta.get("awakening", 0)
        new_record += viewer_delta.get("record", 0)
        trigger_suffix = f" + 視聴者反応({viewer_delta.get('reason', '')})"
    else:
        trigger_suffix = ""

    db.append_parameters(
        episode_number=episode_number,
        trust=new_trust,
        awakening=new_awakening,
        record=new_record,
        trigger_event=delta.get("trigger_event", "") + trigger_suffix,
    )

    # L2記憶更新（上で計算済みの値を再利用し、APIコールを節約）
    l2_entry = {
        "話数": episode_number,
        "タイトル": plot.get("title", ""),
        "要約": plot.get("main_objective", ""),
        "未回収の伏線": ", ".join(
            [fs.get("description", "") for fs in plot.get("foreshadowing_added", [])]
        ),
        "シンジの状態": "(自動更新)",
        "ナギサの状態": "(自動更新)",
        "話の終わりの信頼値": new_trust,
        "話の終わりの覚醒値": new_awakening,
    }
    db.append_memory_l2(l2_entry)
    print("  → 伏線・パラメータ・L2記憶の更新完了")


# ===================================================================
# STEP 6: Config更新・完了レポート
# ===================================================================

def step_finalize(db: SoulRebootDB, episode_number: int, plot: dict,
                  advance_episode: bool = True, analytics_summary: dict | None = None) -> None:
    """次の話数をConfigに書き込み、完了レポートを出力する"""
    print(f"\n[FINALIZE] STEP 6: 完了処理...")

    # 次のエピソード番号に更新（--force 再生成時はスキップ）
    if advance_episode:
        db.set_config("CURRENT_EPISODE", episode_number + 1)
    else:
        print(f"  [FORCE再生成] CURRENT_EPISODE は変更しません")

    # 完了レポート
    print("\n" + "=" * 60)
    print(f"DONE: 第{episode_number}話 生成完了！")
    print(f"   タイトル: {_safe_encode(str(plot.get('title', '')))}")
    print(f"   感情曲線: {_safe_encode(str(plot.get('emotional_curve', '')))}")
    print(f"   クリフハンガー: {_safe_encode(plot.get('cliffhanger', ''), 40)}...")
    if analytics_summary and analytics_summary.get("episodes_fetched", 0) > 0:
        print(f"   Analytics: {analytics_summary['episodes_fetched']}話分収集 / 新規コメント{analytics_summary.get('comments_collected', 0)}件")
    print(f"\n[次のアクション] スプレッドシートを確認してください:")
    print(f"   1. [Episodes] タイトル・プロットの確認と修正")
    print(f"   2. [Scripts] 台本の確認（approved=TRUEに変更で承認）")
    print(f"   3. [Comments] 採用コメントの手動調整")
    print(f"   4. [Assets] 画像/音声生成の承認または再生成指示")
    print("=" * 60)


# ===================================================================
# メインエントリポイント
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Soul Reboot 自律生成エンジン")
    parser.add_argument(
        "--episode", type=int, default=None,
        help="生成する話数（省略時はConfigシートの CURRENT_EPISODE を使用）"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="既存の台本データを削除してから再生成する（CURRENT_EPISODEは変更しない）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Soul Reboot - 自律生成エンジン起動")
    print(f"   実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("ERROR: 環境変数 GEMINI_API_KEY が設定されていません")
        print("   set GEMINI_API_KEY=あなたのAPIキー  を実行してください")
        sys.exit(1)

    # DB接続
    # ※ SPREADSHEET_ID は環境変数 または service_account.json と同ディレクトリの .env から取得
    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("ERROR: 環境変数 SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        sys.exit(1)

    db = SoulRebootDB(spreadsheet_id)
    config = db.get_config()

    # 話数の決定
    episode_number = args.episode or int(config.get("CURRENT_EPISODE", 1))
    print(f"\n[EPISODE]: 第{episode_number}話")

    # --force: 既存データを削除してから再生成
    if args.force:
        print(f"\n[FORCE] 第{episode_number}話の既存台本データを削除します...")
        deleted = db.delete_script_lines_by_episode(episode_number)
        print(f"  → {deleted}行削除完了")

    # 各ステップを順番に実行
    current_step = "初期化"
    start_time = time.time()
    try:
        current_step = "ニュース収集"
        news = step_collect_news(db, config)
        current_step = "YouTube Analytics収集"
        analytics_summary = step_collect_analytics(db, config)
        current_step = "コメントスコアリング"
        top_comments = step_score_comments(db)
        current_step = "プロット生成 (Architect)"
        story_date_info = _get_story_date_info(episode_number)
        plot = step_architect(db, config, episode_number, news, top_comments)
        current_step = "台本生成 (Writer)"
        script_lines = step_writer(db, config, episode_number, plot, story_date_info=story_date_info)
        current_step = "台本監修 (Editor)"
        QUALITY_GATE_THRESHOLD = 300
        MAX_RETRY = 1
        for retry in range(MAX_RETRY + 1):
            script_lines, quality_score = step_editor(db, episode_number, plot, script_lines)
            total = quality_score.get("total", 999)
            if total >= QUALITY_GATE_THRESHOLD or retry >= MAX_RETRY:
                if total < QUALITY_GATE_THRESHOLD:
                    print(f"  [QUALITY GATE] スコア{total}点 < {QUALITY_GATE_THRESHOLD}点。リトライ上限に達したため続行。")
                break
            print(f"  [QUALITY GATE] スコア{total}点 < {QUALITY_GATE_THRESHOLD}点。Architectから再生成します（リトライ {retry+1}/{MAX_RETRY}）")
            issues_text = "\n".join(quality_score.get("issues", []))
            plot = step_architect(db, config, episode_number, news, top_comments,
                                  quality_feedback=issues_text)
            script_lines = step_writer(db, config, episode_number, plot, story_date_info=story_date_info)
        current_step = "メタデータ更新"
        step_update_metadata(db, episode_number, plot)
        current_step = "完了処理"
        step_finalize(db, episode_number, plot, advance_episode=not args.force, analytics_summary=analytics_summary)
        # 台本の総文字数（セリフ・地の文のみ集計）
        script_char_count = sum(
            len(line.get("セリフ・地の文", "")) for line in script_lines
        )
        notify_success(
            episode_number=episode_number,
            title=plot.get("title", ""),
            cliffhanger=plot.get("cliffhanger", ""),
            elapsed_seconds=time.time() - start_time,
            script_char_count=script_char_count,
        )
        # Phase B 自動トリガー用にエピソード番号を書き出す
        with open("episode_number.txt", "w") as f:
            f.write(str(episode_number))
    except Exception as e:
        notify_error(episode_number=episode_number, step=current_step, error=e)
        raise


if __name__ == "__main__":
    main()

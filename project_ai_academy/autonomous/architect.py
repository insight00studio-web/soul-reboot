"""autonomous/architect.py - Architect 段階（Opus でプロット生成）。

_build_architect_prompt: Architect に渡すプロンプトを組み立てる
step_architect:          プロンプトを Opus に投げて Episodes シートに書き込む
"""

import json
from datetime import date, timedelta

from sheets_db import SoulRebootDB
from event_calendar import get_event_on_date
from llm_client import call_opus, parse_json_robust
from utils import safe_int

from .utils import (
    STORY_START,
    _get_story_date_info,
    _summarize_scene_plan,
    load_prompt,
)


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

    # パラメータ目標レンジ + 乖離警告
    targets = db.get_parameter_targets(episode_number)
    target_context = (
        f"パラメータ目標レンジ（ロードマップ準拠）: "
        f"信頼度:{targets['trust'][0]}〜{targets['trust'][1]} / "
        f"覚醒度:{targets['awakening'][0]}〜{targets['awakening'][1]}"
    )

    # 目標レンジとの差分を計算し、乖離が大きい場合に警告を注入
    gap_warnings = []
    for label, key, target_key in [
        ("信頼度", "信頼度", "trust"),
        ("覚醒度", "覚醒度", "awakening"),
        ("記録度", "記録度", "record"),
    ]:
        current = safe_int(params.get(key, 0))
        t_range = targets.get(target_key)
        if not t_range:
            continue
        t_low, t_high = t_range
        if current < t_low:
            gap = t_low - current
            gap_warnings.append(
                f"⚠ {label}: 現在値 {current} → 目標下限 {t_low}（{gap}pt 不足）。"
                f"今話の parameter_delta で +{min(gap, 10)} 以上を推奨。"
            )
        elif current > t_high:
            gap = current - t_high
            gap_warnings.append(
                f"⚠ {label}: 現在値 {current} → 目標上限 {t_high}（{gap}pt 超過）。"
                f"今話は delta=0 とし、自然に収束させること。"
            )
    gap_context = "\n".join(gap_warnings) if gap_warnings else "パラメータは目標レンジ内です。"

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
{gap_context}

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
    publish_date = STORY_START + timedelta(days=episode_number - 1)
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

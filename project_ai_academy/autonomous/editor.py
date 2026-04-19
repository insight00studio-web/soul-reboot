"""autonomous/editor.py - Editor 段階（Opus で台本監修・品質スコアリング）。"""

import json

from sheets_db import SoulRebootDB
from llm_client import call_opus, parse_json_robust
from utils import safe_int

from .memory import build_narrative_context
from .utils import load_prompt


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

    # narrative/ 正典コンテキスト（character_bible・arc_plan・前話状態）を Editor にも渡す
    narrative_section = ""
    try:
        narrative_ctx = build_narrative_context(episode_number)
        if narrative_ctx:
            narrative_section = f"""
---
## 物語正典コンテキスト（narrative/ 層 — 台本がここから逸脱していないか検査すること）

{narrative_ctx}
"""
    except Exception as e:
        print(f"  [EDITOR] WARN: narrative コンテキスト構築に失敗: {e}（スキップして続行）")

    full_prompt = f"""
{editor_base}

---
## プロット（Architectが設計）

{plot_json}

---
## 現在の台本（Writerが生成）

{script_json}
{narrative_section}
---
## 整合性チェック（Phase 3 新設）

上の「物語正典コンテキスト」と台本を照合し、以下を検出して `consistency.issues` に列挙すること:

1. **キャラ口調逸脱**: character_bible の NG 口調がナギサ/シンジのセリフに混入していないか。特にナギサの「お役に立てて嬉しいです」「AIとして〜」「処理します」は絶対禁止。
2. **成長段階の逸脱**: 現在の arc_phase の「禁止される変化」に該当する描写が無いか（例: Phase 1 でナギサが自分を AI と疑う／Phase 3 でシンジが軽口で流す）。
3. **伏線の矛盾**: foreshadowing_resolved で回収したはずの伏線を再度開く描写が無いか。
4. **arc_plan 準拠**: 強制イベント Day（Day 10, 15, 23, 29）の該当Dayで、指定イベントが発生しているか（該当Day以外なら検査不要）。

---
## 出力フォーマット

以下のJSON形式で出力してください。品質スコアと整合性チェック、修正後の台本の両方を含めること。
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
  "consistency": {{
    "character_voice_ok": true,
    "growth_stage_ok": true,
    "foreshadowing_ok": true,
    "arc_event_ok": true,
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

    # 整合性チェック結果（Phase 3 新設）
    if isinstance(edited, dict):
        consistency = edited.get("consistency") or {}
        cons_issues = consistency.get("issues") or []
        if cons_issues:
            print(f"  → 整合性: NG {len(cons_issues)}件")
            for issue in cons_issues:
                print(f"    ! {issue}")
        else:
            checks = [
                ("口調", consistency.get("character_voice_ok")),
                ("成長段階", consistency.get("growth_stage_ok")),
                ("伏線", consistency.get("foreshadowing_ok")),
                ("arc_event", consistency.get("arc_event_ok")),
            ]
            ok_flags = [n for n, v in checks if v is True]
            if ok_flags:
                print(f"  → 整合性 OK: {', '.join(ok_flags)}")

    # スプレッドシートを上書き
    db.replace_script_lines(episode_number, edited_lines)
    print(f"  → スプレッドシート更新完了")

    return edited_lines, quality_score

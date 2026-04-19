"""autonomous/editor.py - Editor 段階（Opus で台本監修・品質スコアリング）。"""

import json

from sheets_db import SoulRebootDB
from llm_client import call_opus, parse_json_robust
from utils import safe_int

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

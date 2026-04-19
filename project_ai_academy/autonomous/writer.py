"""autonomous/writer.py - Writer 段階（Gemini で台本生成）。"""

import json

from sheets_db import SoulRebootDB
from llm_client import call_gemini

from .utils import load_prompt


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

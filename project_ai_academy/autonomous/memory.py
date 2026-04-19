"""autonomous/memory.py - narrative/ 層を Architect に注入する窓口。

Phase 3 で新設。既存の Sheets ベース L1/L2 記憶に加え、
  - narrative/arc_plan.md        ... 29話弧の骨格
  - narrative/character_bible.md ... キャラ不変要素・成長曲線
  - narrative/episode_memory/ep_{NN}.(yaml|json) ... 話ごとの構造化記憶
を読み込み、Architect プロンプト末尾に `<previous_episode_state>` 等の
構造化セクションとして注入する。

PyYAML が無くても動くよう、episode_memory は .yaml / .json 両対応。
書き出しは PyYAML が入っていれば .yaml、なければ .json。
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:
    yaml = None
    _HAS_YAML = False

from .utils import BASE_DIR

NARRATIVE_DIR = os.path.join(BASE_DIR, "narrative")
ARC_PLAN_PATH = os.path.join(NARRATIVE_DIR, "arc_plan.md")
CHARACTER_BIBLE_PATH = os.path.join(NARRATIVE_DIR, "character_bible.md")
EPISODE_MEMORY_DIR = os.path.join(NARRATIVE_DIR, "episode_memory")


def get_arc_phase(episode_number: int) -> str:
    """エピソード番号から arc フェーズ識別子を返す（arc_plan.md の区切りに準拠）"""
    if episode_number <= 9:
        return "PHASE_1_happy_misrecognition"
    if episode_number <= 21:
        return "PHASE_2_soul_noise"
    if episode_number <= 28:
        return "PHASE_3_sanctuary_collapse"
    return "PHASE_4_ending"


def _read_file_safe(path: str) -> str:
    """ファイルを読む。無ければ空文字を返す（narrative/ 未整備時のフェイルセーフ）"""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _find_episode_memory_file(episode_number: int) -> str | None:
    """ep_{NN}.yaml または ep_{NN}.json を探す。無ければ None"""
    base = os.path.join(EPISODE_MEMORY_DIR, f"ep_{episode_number:02d}")
    for ext in (".yaml", ".yml", ".json"):
        p = base + ext
        if os.path.exists(p):
            return p
    return None


def _load_episode_memory(episode_number: int) -> dict | None:
    """ep_{NN}.(yaml|json) を読み込む。無ければ None"""
    path = _find_episode_memory_file(episode_number)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if path.endswith((".yaml", ".yml")):
            if not _HAS_YAML:
                return None
            return yaml.safe_load(content)
        return json.loads(content)
    except Exception as e:
        print(f"  [MEMORY] WARN: {path} 読み込み失敗: {e}")
        return None


def _format_episode_memory_section(mem: dict) -> str:
    """ep_{N}.yaml の内容を Architect 向けに整形"""
    lines = []
    lines.append(f"- 前話タイトル: 第{mem.get('episode', '?')}話『{mem.get('title', '')}』")
    if one_liner := mem.get("one_line_summary"):
        lines.append(f"- 1文要約: {one_liner}")
    if hook := mem.get("next_ep_hook"):
        lines.append(f"- 次話への繋ぎ: {hook}")
    if cliff := mem.get("cliffhanger"):
        lines.append(f"- 前話末のクリフハンガー: {cliff}")

    cs = mem.get("character_state") or {}
    if nagisa := cs.get("NAGISA"):
        lines.append(
            f"- ナギサ話末状態: {nagisa.get('emotion', '')} / AI自覚:{nagisa.get('awareness_of_ai', '')} / 対シンジ:{nagisa.get('relation_to_SHINJI', '')}"
        )
    if shinji := cs.get("SHINJI"):
        lines.append(
            f"- シンジ話末状態: {shinji.get('emotion', '')} / 内心:{shinji.get('hidden_motive', '')} / 対ナギサ:{shinji.get('relation_to_NAGISA', '')}"
        )

    if events := mem.get("key_events"):
        lines.append("- 前話の主要イベント:")
        for ev in events[:5]:
            lines.append(f"  * {ev}")
    return "\n".join(lines)


def _extract_phase_section(arc_plan_text: str, phase_key: str) -> str:
    """arc_plan.md から現在フェーズの記述だけを抽出する。

    セクション見出しが無いので、テーブル行と強制イベント行をフェーズ名で絞る簡易実装。
    全文渡してもトークンコストは数百程度なので、現実的には全文注入でも良い。
    """
    # 現状は全文注入（character_bible.md と合わせても 8K 未満）
    return arc_plan_text


def build_narrative_context(episode_number: int) -> str:
    """Architect プロンプトに注入する構造化コンテキストを生成する。

    返り値は「---」で区切られた 4 セクション:
      <arc_position>           現在フェーズの識別子と目的
      <arc_plan>               arc_plan.md 全文（または該当フェーズ抽出）
      <character_bible>        character_bible.md 全文
      <previous_episode_state> ep_{N-1} の構造化要約（存在すれば）

    narrative/ が未整備でも空文字を返さず、可能な範囲で整形する。
    """
    sections: list[str] = []

    # 1. arc_position
    phase = get_arc_phase(episode_number)
    sections.append(
        f"## <arc_position>\n\n"
        f"- エピソード番号: 第{episode_number}話 (Day {episode_number})\n"
        f"- 現在フェーズ: **{phase}**\n"
        f"- このフェーズでの目的・許容変化・禁止変化は下記 character_bible の成長曲線を必ず参照すること。"
    )

    # 2. arc_plan
    arc_plan = _read_file_safe(ARC_PLAN_PATH)
    if arc_plan:
        arc_section = _extract_phase_section(arc_plan, phase)
        sections.append(f"## <arc_plan>\n\n{arc_section}")

    # 3. character_bible
    bible = _read_file_safe(CHARACTER_BIBLE_PATH)
    if bible:
        sections.append(f"## <character_bible>\n\n{bible}")

    # 4. previous_episode_state (ep_{N-1})
    prev_mem = _load_episode_memory(episode_number - 1) if episode_number > 1 else None
    if prev_mem:
        sections.append(
            f"## <previous_episode_state>\n\n{_format_episode_memory_section(prev_mem)}"
        )
    else:
        sections.append(
            "## <previous_episode_state>\n\n"
            "（前話の構造化記憶は未生成。既存の L1/L2 記憶のみを参照すること。）"
        )

    return "\n\n---\n\n".join(sections)


def write_episode_memory(
    episode_number: int,
    plot: dict,
    parameters: dict,
    story_date_info: dict | None = None,
) -> str | None:
    """Phase A 完了時に ep_{NN}.(yaml|json) を書き出す。

    plot (Architect 出力) と parameters (話末値) から構造化して永続化する。
    PyYAML があれば .yaml、なければ .json で保存。
    """
    os.makedirs(EPISODE_MEMORY_DIR, exist_ok=True)

    sd = story_date_info or {}
    ps = plot.get("plot_summary") or {}
    scenes = plot.get("scene_plan") or []

    # 1文要約: main_objective を使う（無ければ title）
    one_liner = plot.get("main_objective") or plot.get("title", "")

    memory: dict[str, Any] = {
        "episode": episode_number,
        "date": sd.get("story_date_iso") or sd.get("story_date", ""),
        "arc_phase": get_arc_phase(episode_number),
        "title": plot.get("title", ""),
        "one_line_summary": one_liner,
        "key_events": [
            ps.get("introduction", ""),
            ps.get("development", ""),
            ps.get("climax", ""),
        ],
        "character_state": {
            "NAGISA": {
                "emotion": "",
                "awareness_of_ai": "",
                "relation_to_SHINJI": "",
            },
            "SHINJI": {
                "emotion": "",
                "hidden_motive": "",
                "relation_to_NAGISA": "",
            },
        },
        "foreshadowing": {
            "opened": [
                fs.get("description", "") for fs in plot.get("foreshadowing_added", [])
            ],
            "resolved": [
                r.get("id", "") for r in plot.get("foreshadowing_resolved", [])
            ],
        },
        "parameters": {
            "trust": parameters.get("trust", 0),
            "awakening": parameters.get("awakening", 0),
            "record": parameters.get("record", 0),
        },
        "cliffhanger": plot.get("cliffhanger", ""),
        "next_ep_hook": plot.get("cliffhanger", ""),
        "used": {
            "comedy_pattern": plot.get("comedy_pattern", ""),
            "structure_type": plot.get("structure_type", ""),
            "scene_locations": [s.get("location", "") for s in scenes],
        },
    }

    if _HAS_YAML:
        path = os.path.join(EPISODE_MEMORY_DIR, f"ep_{episode_number:02d}.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(memory, f, allow_unicode=True, sort_keys=False)
    else:
        path = os.path.join(EPISODE_MEMORY_DIR, f"ep_{episode_number:02d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)

    return path

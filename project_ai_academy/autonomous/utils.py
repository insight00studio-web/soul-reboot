"""autonomous/utils.py - Phase A で共通利用するヘルパ。

load_prompt, 物語内日付の計算、scene_plan のサマライズなど
モジュール間で共通する純粋関数・定数のみを置く。
"""

import os
import sys
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")


def load_prompt(filename: str) -> str:
    """promptsフォルダからMarkdownファイルを読み込む"""
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _safe_encode(text: str, length: int = 9999) -> str:
    """cp932等のターミナルで表示できない文字をエスケープする"""
    return text[:length].encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")


STORY_START = date(2026, 4, 8)  # Day 1 = 入学式

NATIONAL_HOLIDAYS = {
    date(2026, 4, 29),  # 昭和の日
    date(2026, 5, 3),   # 憲法記念日
    date(2026, 5, 4),   # みどりの日
    date(2026, 5, 5),   # こどもの日
    date(2026, 5, 6),   # 振替休日
}

WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]


def _get_story_date_info(episode_number: int) -> dict:
    """物語内日付・曜日・服装を計算する"""
    story_date = STORY_START + timedelta(days=episode_number - 1)
    weekday = WEEKDAYS_JA[story_date.weekday()]
    is_holiday = story_date in NATIONAL_HOLIDAYS
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

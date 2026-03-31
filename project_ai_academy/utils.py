"""
utils.py
Soul Reboot - 共通ユーティリティ

プロジェクト全体で共有される小さなヘルパー関数群。
"""

import os
import re


def safe_int(val, default: int = 0) -> int:
    """安全な int 変換。空文字列や None でもクラッシュしない"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def find_japanese_font(bold_first: bool = True) -> str:
    """利用可能な日本語フォントを検索（Windows / Linux 両対応）

    Args:
        bold_first: True なら太字フォントを優先的に返す
    """
    if bold_first:
        candidates = [
            # Windows (Bold first)
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            # Linux (Bold first)
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/fonts-ipafont-gothic/ipag.ttf",
        ]
    else:
        candidates = [
            # Windows
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
            # Linux
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/fonts-ipafont-gothic/ipag.ttf",
            "/usr/share/fonts/truetype/fonts-ipafont-gothic/ipagp.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "日本語フォントが見つかりません。Windows または Linux (fonts-noto-cjk) が必要です。"
    )


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

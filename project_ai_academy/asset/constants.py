"""asset/constants.py - アセット生成全般で共有される定数。"""

# レート制限・リトライ設定
RATE_LIMIT_WAIT = 21       # 生成成功後のレート制限回避待機（秒）
TTS_RETRY_WAIT_429 = 60    # TTS 429エラー時のリトライ待機（秒）
IMAGE_RETRY_WAIT_429 = 65  # 画像生成 429エラー時のリトライ待機（秒）
MAX_RETRIES = 5            # 生成リトライ上限

# TTS マルチスピーカーバッチング設定
TTS_BATCH_ENABLED = True       # False で完全に従来動作へロールバック
BATCH_MAX_DURATION_SEC = 90    # 1バッチの想定総再生秒（drift 回避）
BATCH_MIN_LINES = 2            # バッチ対象の最小行数
BATCH_TONE_DOMINANCE = 0.0     # 0.0 でトーン制約撤廃（最頻トーンで一括生成、行ごとの感情差は妥協）
TEXT_TO_DURATION_RATIO = 0.15  # 文字数 × この値 = 想定再生秒（バッチ尺見積用）

# 音声分割（無音検出）設定
SILENCE_THRESHOLD_DB = -40.0   # この値以下を無音とみなす
SILENCE_MIN_SEC = 0.25         # この秒数以上の無音を分割点とみなす（短めにして検出率UP）

# 感情トーン → TTS emotion タグのマップ
TONE_TAG_MAP: dict[str, str] = {
    "明るい": "excited",
    "喜び": "happy",
    "悲しい": "sad",
    "怒り": "angry",
    "驚き": "amazed",
    "恐れ": "panicked",
    "嫌悪": "scornful",
    "震え": "trembling",
    "毒舌": "sarcastic",
    "ツッコミ": "playful",
    "微照れ（即否定）": "playful",
    "冷静分析": "serious",
    "静か": "measured",
    "観察": "thoughtful",
    "不穏": "menacing",
    "共感": "empathetic",
    "好奇": "curious",
    "憂鬱": "tired",
    "決意": "determined",
    "笑い": "laughs",
    "ため息": "sighs",
    "ささやき": "whispers",
}

# 場所キーワード辞書（画像プロンプトから場所を正規化するため）
LOCATION_KEYWORD_MAP = [
    ("classroom",     ["classroom", "教室"]),
    ("corridor",      ["hallway", "corridor", "廊下"]),
    ("cafe",          ["cafe", "café", "starbucks", "coffee shop", "スタバ", "カフェ"]),
    ("library",       ["library", "図書館", "図書室"]),
    ("park",          ["park", "公園"]),
    ("station",       ["station", "駅"]),
    ("rooftop",       ["rooftop", "屋上"]),
    ("gym",           ["gymnasium", "体育館"]),
    ("home",          ["living room", "bedroom", "自宅", "リビング", "自室"]),
    ("store",         ["shopping", "コンビニ", "ショッピング", "モール"]),
    ("restaurant",    ["restaurant", "dining", "cafeteria", "食堂", "レストラン"]),
    ("nurse_office",  ["infirmary", "保健室"]),
    ("entrance",      ["shoe locker", "下駄箱", "昇降口", "校門"]),
]

# 私服マスター生成プロンプト定義 {char_key: {outfit_key: (outfit_desc, context)}}
OUTFIT_DEFINITIONS: dict[str, dict[str, tuple[str, str]]] = {
    "NAGISA": {
        "spring":  ("mint green oversized hoodie, white inner blouse, light blue slim jeans, white sneakers",
                    "spring casual, soft pastel tones"),
        "summer":  ("white sleeveless blouse, light blue denim shorts, casual sandals",
                    "summer casual, light and breezy"),
        "winter":  ("cream turtleneck sweater, dark plaid midi skirt, caramel brown cardigan, ankle boots",
                    "fall/winter casual, warm layered look"),
        "indoor":  ("soft lavender oversized hoodie, light gray sweatpants, white socks",
                    "cozy indoor home outfit, relaxed loungewear"),
        "outing":  ("pastel yellow floral blouse, white wide-leg trousers, small shoulder bag, white flats",
                    "smart casual going-out outfit, slightly dressed up"),
    },
    "SHINJI": {
        "spring":  ("navy blue zip-up hoodie, white t-shirt underneath, light khaki chinos, white sneakers",
                    "spring casual, comfortable and relaxed"),
        "summer":  ("plain white t-shirt, light denim shorts, casual sneakers",
                    "summer casual, simple and cool"),
        "winter":  ("heather gray chunky knit sweater, dark navy jeans, dark sneakers",
                    "fall/winter casual, warm and cozy"),
        "indoor":  ("soft olive green sweatshirt, light gray joggers, white socks",
                    "cozy home outfit, comfortable loungewear"),
        "outing":  ("light blue Oxford button-up shirt, navy chinos, leather sneakers",
                    "smart casual going-out outfit"),
    },
}

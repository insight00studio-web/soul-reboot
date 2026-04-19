"""sheets/schema.py - シート名定数と認証ファイルパス。"""

import os

# OAuth2クライアントIDのパス（同ディレクトリに配置）
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "credentials.json")

# 認証トークンのキャッシュ先（自動生成・自動更新される）
TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "token.json")

# シート名の定数（タイポ防止）
SHEET_EPISODES      = "📋 Episodes"
SHEET_SCRIPTS       = "📜 Scripts"
SHEET_FORESHADOWING = "🔮 Foreshadowing"
SHEET_COMMENTS      = "💬 Comments"
SHEET_PARAMETERS    = "📊 Parameters"
SHEET_ASSETS        = "🎵 Assets"
SHEET_NEWS          = "📰 News"
SHEET_MEMORY_L2     = "📖 Memory_L2"
SHEET_CONFIG        = "⚙️ Config"
SHEET_ANALYTICS     = "📈 Analytics"

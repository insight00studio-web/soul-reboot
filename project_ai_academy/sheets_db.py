"""sheets_db.py - sheets パッケージの facade。

実装は sheets/ 以下に分割されている:
  - sheets/schema.py  : シート名定数・認証ファイルパス
  - sheets/reader.py  : 読み取り系メソッド（ReaderMixin）
  - sheets/writer.py  : 書き込み系メソッド（WriterMixin）
  - sheets/db.py      : SoulRebootDB 本体

既存コードの `from sheets_db import SoulRebootDB` や
`from sheets_db import SHEET_EPISODES` はこのファイル経由で引き続き動作する。
"""

from sheets import (
    SoulRebootDB,
    CREDENTIALS_FILE,
    TOKEN_FILE,
    SHEET_EPISODES,
    SHEET_SCRIPTS,
    SHEET_FORESHADOWING,
    SHEET_COMMENTS,
    SHEET_PARAMETERS,
    SHEET_ASSETS,
    SHEET_NEWS,
    SHEET_MEMORY_L2,
    SHEET_CONFIG,
    SHEET_ANALYTICS,
)

__all__ = [
    "SoulRebootDB",
    "CREDENTIALS_FILE",
    "TOKEN_FILE",
    "SHEET_EPISODES",
    "SHEET_SCRIPTS",
    "SHEET_FORESHADOWING",
    "SHEET_COMMENTS",
    "SHEET_PARAMETERS",
    "SHEET_ASSETS",
    "SHEET_NEWS",
    "SHEET_MEMORY_L2",
    "SHEET_CONFIG",
    "SHEET_ANALYTICS",
]

"""sheets パッケージ - Google Spreadsheet DB アクセス層。

このパッケージは 3 つの役割に分かれている:
  - schema: シート名定数・認証ファイルパス
  - reader: 読み取り系メソッド（ReaderMixin）
  - writer: 書き込み系メソッド（WriterMixin）
  - db: SoulRebootDB 本体（上記 2 つの Mixin を合成）

既存コードは `from sheets_db import SoulRebootDB` を使い続けて良い。
sheets_db.py はこのパッケージの facade である。
"""

from .db import SoulRebootDB
from .schema import (
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

"""sheets/db.py - SoulRebootDB 本体。

ReaderMixin と WriterMixin を合成する薄いクラス。
初期化と _sheet() だけが本体の責務。
"""

import gspread

from .reader import ReaderMixin
from .schema import CREDENTIALS_FILE, TOKEN_FILE
from .writer import WriterMixin


class SoulRebootDB(ReaderMixin, WriterMixin):
    """Google Spreadsheetへの全アクセスを管理するクラス。

    ReaderMixin（読み）と WriterMixin（書き）を合成している。
    メソッドの実装は各 Mixin を参照。
    """

    def __init__(self, spreadsheet_id: str):
        """
        OAuth2（個人Googleアカウント）でスプレッドシートに接続する。
        初回のみブラウザが開いてログインが必要。
        以降は token.json が自動的に使われるため、ブラウザ不要。

        Args:
            spreadsheet_id: Google SpreadsheetのID
                            (URLの /d/ と /edit の間の文字列)
        """
        client = gspread.oauth(
            credentials_filename=CREDENTIALS_FILE,
            authorized_user_filename=TOKEN_FILE,
        )
        self.spreadsheet = client.open_by_key(spreadsheet_id)
        self._config_cache: dict | None = None
        print(f"CONNECTED: スプレッドシート接続成功: {self.spreadsheet.title}")

    def _sheet(self, name: str) -> gspread.Worksheet:
        """シート名からワークシートを取得"""
        return self.spreadsheet.worksheet(name)

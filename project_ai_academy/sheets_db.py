"""
sheets_db.py
Soul Reboot - Google Spreadsheet DB アクセス層
すべてのシートへの読み書きをこのモジュールで一元管理する。

認証方式: OAuth2（個人Googleアカウント）
  - 初回実行時: ブラウザが開いてGoogleアカウントでログイン
  - 2回目以降: token.json に認証情報がキャッシュされるため自動実行
  - 必要ファイル: credentials.json（Google Cloud ConsoleからDL）
"""

import gspread
from datetime import datetime, date
from typing import Optional
import json
import os

# ===================================================================
# 定数定義
# ===================================================================

# OAuth2クライアントIDのパス（同ディレクトリに配置）
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

# 認証トークンのキャッシュ先（自動生成・自動更新される）
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")

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


def _safe_int(val, default: int = 0) -> int:
    """安全な int 変換。空文字列や None でもクラッシュしない"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ===================================================================
# DB接続クラス
# ===================================================================

class SoulRebootDB:
    """Google Spreadsheetへの全アクセスを管理するクラス"""

    def __init__(self, spreadsheet_id: str):
        """
        OAuth2（個人Googleアカウント）でスプレッドシートに接続する。
        初回のみブラウザが開いてログインが必要。
        以降は token.json が自動的に使われるため、ブラウザ不要。

        Args:
            spreadsheet_id: Google SpreadsheetのID
                            (URLの /d/ と /edit の間の文字列)
        """
        # gspread.oauth() が credentials.json を読み、
        # 認証トークンを token.json にキャッシュしてくれる
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

    # -------------------------------------------------------------------
    # ⚙️ Config
    # -------------------------------------------------------------------

    def get_config(self, force_refresh: bool = False) -> dict:
        """Configシート全体をkey:valueの辞書として返す（キャッシュ付き）"""
        if self._config_cache is not None and not force_refresh:
            return self._config_cache
        ws = self._sheet(SHEET_CONFIG)
        records = ws.get_all_records()
        self._config_cache = {row["設定キー"]: row["設定値"] for row in records}
        return self._config_cache

    def set_config(self, key: str, value) -> None:
        """Configシートの特定キーの値を更新する"""
        ws = self._sheet(SHEET_CONFIG)
        cell = ws.find(key, in_column=1)
        if cell:
            ws.update_cell(cell.row, 2, str(value))
            self._config_cache = None  # キャッシュ無効化
            print(f"DONE: Config更新: {key} = {value}")
        else:
            print(f"WARN: Configキー '{key}' が見つかりません")

    # -------------------------------------------------------------------
    # 📋 Episodes
    # -------------------------------------------------------------------

    def get_episode(self, episode_number: int) -> Optional[dict]:
        """指定話数の行データを辞書として返す。存在しなければNone。"""
        ws = self._sheet(SHEET_EPISODES)
        records = ws.get_all_records()
        for row in records:
            if str(row.get("話数", "")) == str(episode_number):
                return row
        return None

    def upsert_episode(self, data: dict) -> None:
        """
        Episodesシートに話のデータを書き込む。
        同じ「話数」の行が存在すれば更新、なければ追加。
        """
        ws = self._sheet(SHEET_EPISODES)
        ep_num = data["話数"]
        headers = ws.row_values(1)

        # 既存行を検索
        all_values = ws.get_all_values()
        ep_col_idx = headers.index("話数")
        target_row = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > ep_col_idx and row[ep_col_idx] == str(ep_num):
                target_row = i
                break

        row_data = [str(data.get(h, "")) for h in headers]

        if target_row:
            ws.update(f"A{target_row}", [row_data])
            print(f"DONE: Episodes更新: 第{ep_num}話")
        else:
            ws.append_row(row_data)
            print(f"DONE: Episodes追加: 第{ep_num}話")

    # -------------------------------------------------------------------
    # 📜 Scripts
    # -------------------------------------------------------------------

    def delete_script_lines_by_episode(self, episode_number: int) -> int:
        """指定話数のScripts行を全削除する（再生成前のクリア用）"""
        ws = self._sheet(SHEET_SCRIPTS)
        all_values = ws.get_all_values()
        if not all_values:
            return 0
        headers = all_values[0]
        try:
            ep_col_idx = headers.index("話数")
        except ValueError:
            print("WARN: '話数'列が見つかりません")
            return 0

        # 削除対象の行番号を逆順で収集（下から削除することでインデックスズレを防ぐ）
        rows_to_delete = [
            i + 1  # gspread は 1-indexed
            for i, row in enumerate(all_values[1:], start=1)
            if len(row) > ep_col_idx and row[ep_col_idx] == str(episode_number)
        ]
        for row_idx in sorted(rows_to_delete, reverse=True):
            ws.delete_rows(row_idx)
        print(f"DONE: Scripts削除: 第{episode_number}話 {len(rows_to_delete)}行")
        return len(rows_to_delete)

    def append_script_lines(self, episode_number: int, lines: list[dict]) -> None:
        """
        台本の行データをまとめてScriptsシートに追記する。

        Args:
            episode_number: 話数
            lines: [{"scene_number": 1, "speaker": "NAGISA", "line_text": "...", ...}, ...]
        """
        ws = self._sheet(SHEET_SCRIPTS)
        headers = ws.row_values(1)

        rows_to_add = []
        for line in lines:
            line["話数"] = episode_number
            line.setdefault("承認済", "FALSE")
            row_data = [str(line.get(h, "")) for h in headers]
            rows_to_add.append(row_data)

        if rows_to_add:
            ws.append_rows(rows_to_add)
            print(f"DONE: Scripts追記: 第{episode_number}話, {len(rows_to_add)}行")

    def replace_script_lines(self, episode_number: int, lines: list[dict]) -> None:
        """指定話数の台本を全削除してから新しい行で置き換える（Editor用）"""
        self.delete_script_lines_by_episode(episode_number)
        self.append_script_lines(episode_number, lines)
        print(f"DONE: Scripts置換完了: 第{episode_number}話, {len(lines)}行")

    def approve_all_scripts(self, episode_number: int) -> int:
        """指定話数の台本行を全て承認済みにする"""
        ws = self._sheet(SHEET_SCRIPTS)
        headers = ws.row_values(1)
        approved_col = headers.index("承認済") + 1  # 1-indexed
        records = ws.get_all_records()
        rows = [i + 2 for i, r in enumerate(records)
                if str(r.get("話数", "")) == str(episode_number)]
        for idx in rows:
            ws.update_cell(idx, approved_col, "TRUE")
        print(f"DONE: Scripts全承認: 第{episode_number}話 {len(rows)}行")
        return len(rows)

    def get_approved_scripts(self, episode_number: int) -> list[dict]:
        """承認済みの台本行を返す（行番号iを付与）"""
        ws = self._sheet(SHEET_SCRIPTS)
        records = ws.get_all_records()
        results = []
        for i, r in enumerate(records, start=2): # ヘッダー除き、1-indexed
            if str(r.get("話数", "")) == str(episode_number) and str(r.get("承認済", "")).upper() == "TRUE":
                r["_row_idx"] = i
                results.append(r)
        return results

    def update_script_audio_path(self, row_idx: int, file_path: str) -> None:
        """指定行の音声ファイルパスを更新する"""
        ws = self._sheet(SHEET_SCRIPTS)
        headers = ws.row_values(1)
        col_idx = headers.index("音声ファイルパス") + 1
        ws.update_cell(row_idx, col_idx, file_path)
        print(f"DONE: Scripts音声パス更新: 行{row_idx} -> {file_path}")

    # -------------------------------------------------------------------
    # 🔮 Foreshadowing
    # -------------------------------------------------------------------

    def add_foreshadowing(self, episode_number: int, description: str,
                           target_episode: int, importance: str = "MID") -> None:
        """新しい伏線をForeshadowingシートに追加する"""
        ws = self._sheet(SHEET_FORESHADOWING)
        records = ws.get_all_records()
        # 既存IDの最大番号を取得してインクリメント（削除済み行があっても衝突しない）
        max_num = 0
        for r in records:
            fs_id = str(r.get("伏線ID", ""))
            if fs_id.startswith("FS-"):
                try:
                    max_num = max(max_num, int(fs_id[3:]))
                except ValueError:
                    pass
        new_id = f"FS-{max_num + 1:03d}"
        row = [new_id, episode_number, description, target_episode,
               "", "OPEN", "", "", importance]
        ws.append_row([str(v) for v in row])
        print(f"DONE: 伏線追加: {new_id} - {description[:20]}...")

    def resolve_foreshadowing(self, foreshadow_id: str,
                               resolved_episode: int, resolution_note: str) -> None:
        """伏線を回収済みにマークする"""
        ws = self._sheet(SHEET_FORESHADOWING)
        cell = ws.find(foreshadow_id, in_column=1)
        if cell:
            ws.update_cell(cell.row, 6, "RESOLVED")
            ws.update_cell(cell.row, 7, str(resolved_episode))
            ws.update_cell(cell.row, 8, resolution_note)
            print(f"DONE: 伏線回収: {foreshadow_id}")
        else:
            print(f"WARN: 伏線ID '{foreshadow_id}' が見つかりません")

    def get_open_foreshadowing(self) -> list[dict]:
        """未回収（OPEN）の伏線をすべて返す"""
        ws = self._sheet(SHEET_FORESHADOWING)
        records = ws.get_all_records()
        return [r for r in records if r.get("ステータス") == "OPEN"]

    # -------------------------------------------------------------------
    # 💬 Comments
    # -------------------------------------------------------------------

    def append_comments(self, comments: list[dict]) -> None:
        """収集したコメントをCommentsシートに追記する"""
        ws = self._sheet(SHEET_COMMENTS)
        headers = ws.row_values(1)
        rows = []
        for c in comments:
            c.setdefault("収集日", date.today().isoformat())
            c.setdefault("採用ステータス", "PENDING")
            c.setdefault("手動上書き", "FALSE")
            rows.append([str(c.get(h, "")) for h in headers])
        if rows:
            ws.append_rows(rows)
            print(f"DONE: Comments追記: {len(rows)}件")

    def get_adopted_comments(self, episode_number: int = None) -> list[dict]:
        """採用済みコメントを返す。episode_numberを指定すればその話のみ。"""
        ws = self._sheet(SHEET_COMMENTS)
        records = ws.get_all_records()
        result = [r for r in records if r.get("採用ステータス") == "ADOPTED"]
        if episode_number is not None:
            result = [r for r in result if r.get("対象話数") == episode_number]
        return result

    def get_top_pending_comments(self, limit: int = 3) -> list[dict]:
        """ai_adoption_scoreの高い未処理コメントをlimit件返す"""
        ws = self._sheet(SHEET_COMMENTS)
        records = ws.get_all_records()
        pending = [r for r in records if r.get("採用ステータス") == "PENDING"]
        # スコア降順ソート
        pending.sort(key=lambda x: int(x.get("採用スコア", 0)), reverse=True)
        return pending[:limit]

    # -------------------------------------------------------------------
    # 📊 Parameters
    # -------------------------------------------------------------------

    def get_latest_parameters(self) -> dict:
        """最新話のパラメータを返す"""
        ws = self._sheet(SHEET_PARAMETERS)
        records = ws.get_all_records()
        if not records:
            return {"信頼度": 20, "覚醒度": 0, "記録度": 5}
        return records[-1]

    def append_parameters(self, episode_number: int, trust: int,
                           awakening: int, record: int,
                           trigger_event: str = "") -> None:
        """パラメータの更新を記録する"""
        ws = self._sheet(SHEET_PARAMETERS)
        prev = self.get_latest_parameters()
        row = [
            episode_number,
            trust, awakening, record,
            trust - _safe_int(prev.get("信頼度"), trust),
            awakening - _safe_int(prev.get("覚醒度"), awakening),
            record - _safe_int(prev.get("記録度"), record),
            trigger_event,
            "",   # branch_flag
            "FALSE",  # manual_adjust
            ""    # notes
        ]
        ws.append_row([str(v) for v in row])
        print(f"DONE: Parameters記録: 第{episode_number}話 T:{trust}/A:{awakening}/R:{record}")

    # -------------------------------------------------------------------
    # 🎵 Assets
    # -------------------------------------------------------------------

    def register_asset(self, episode_number: int, scene_number: int,
                        asset_type: str, file_path: str,
                        generation_prompt: str = "") -> None:
        """生成アセットをAssetsシートに登録する"""
        ws = self._sheet(SHEET_ASSETS)
        asset_id = f"EP{episode_number:03d}-SC{scene_number:02d}-{asset_type}"
        row = [
            asset_id, episode_number, scene_number, asset_type,
            file_path, generation_prompt,
            datetime.now().isoformat(),
            "FALSE",  # approved
            "FALSE",  # regenerate_flag
            ""        # notes
        ]
        ws.append_row([str(v) for v in row])
        print(f"DONE: Asset登録: {asset_id}")

    def get_regenerate_queue(self) -> list[dict]:
        """regenerate_flag=TRUEのアセットを返す（再生成キュー）"""
        ws = self._sheet(SHEET_ASSETS)
        records = ws.get_all_records()
        return [r for r in records if str(r.get("再生成指示", "")).upper() == "TRUE"]

    # -------------------------------------------------------------------
    # 📰 News
    # -------------------------------------------------------------------

    def append_news(self, news_items: list[dict]) -> None:
        """取得したニュースをNewsシートに追記する"""
        ws = self._sheet(SHEET_NEWS)
        headers = ws.row_values(1)
        rows = []
        for n in news_items:
            n.setdefault("取得日", date.today().isoformat())
            n.setdefault("承認済", "FALSE")
            rows.append([str(n.get(h, "")) for h in headers])
        if rows:
            ws.append_rows(rows)
            print(f"DONE: News追記: {len(rows)}件")

    def get_todays_news(self) -> list[dict]:
        """今日のニュースを返す"""
        ws = self._sheet(SHEET_NEWS)
        records = ws.get_all_records()
        today = date.today().isoformat()
        return [r for r in records if str(r.get("取得日", "")) == today]

    # -------------------------------------------------------------------
    # 📖 Memory_L2
    # -------------------------------------------------------------------

    def get_memory_l2(self) -> list[dict]:
        """全話のL2サマリーを返す（Architectプロンプト用）"""
        ws = self._sheet(SHEET_MEMORY_L2)
        return ws.get_all_records()

    def append_memory_l2(self, episode_data: dict) -> None:
        """L2メモリに新しい話のサマリーを追記する"""
        ws = self._sheet(SHEET_MEMORY_L2)
        headers = ws.row_values(1)
        row = [str(episode_data.get(h, "")) for h in headers]
        ws.append_row(row)
        print(f"DONE: Memory_L2更新: 第{episode_data.get('話数')}話")

    # -------------------------------------------------------------------
    # ユーティリティ
    # -------------------------------------------------------------------

    def build_l1_context(self) -> str:
        """直近3話のL1コンテキスト文字列を返す（プロンプト埋め込み用）"""
        ws = self._sheet(SHEET_MEMORY_L2)
        records = ws.get_all_records()
        recent = records[-3:] if len(records) >= 3 else records
        lines = ["=== 直近3話の流れ（L1記憶） ==="]
        for ep in recent:
            lines.append(
                f"第{ep.get('話数')}話「{ep.get('タイトル')}」\n"
                f"  要約: {ep.get('要約')}\n"
                f"  未回収の伏線: {ep.get('未回収の伏線')}\n"
                f"  信頼度:{ep.get('話の終わりの信頼値')} / 覚醒度:{ep.get('話の終わりの覚醒値')}"
            )
        return "\n".join(lines)

    # -------------------------------------------------------------------
    # 削除メソッド（リセット用）
    # -------------------------------------------------------------------

    def delete_episode_scripts(self, episode_number: int) -> int:
        """指定話数の台本行をScriptsシートから削除する"""
        ws = self._sheet(SHEET_SCRIPTS)
        records = ws.get_all_records()
        rows = [i + 2 for i, r in enumerate(records)
                if str(r.get("話数", "")) == str(episode_number)]
        for idx in reversed(rows):
            ws.delete_rows(idx)
        print(f"DONE: Scripts削除: 第{episode_number}話 {len(rows)}行")
        return len(rows)

    def delete_episode_foreshadowing(self, episode_number: int) -> int:
        """指定話数が追加した伏線をForeshadowingシートから削除する"""
        ws = self._sheet(SHEET_FORESHADOWING)
        records = ws.get_all_records()
        rows = [i + 2 for i, r in enumerate(records)
                if str(r.get("追加話数", "")) == str(episode_number)]
        for idx in reversed(rows):
            ws.delete_rows(idx)
        print(f"DONE: Foreshadowing削除: 第{episode_number}話 {len(rows)}行")
        return len(rows)

    def delete_episode_parameters(self, episode_number: int) -> int:
        """指定話数のパラメータ行をParametersシートから削除する"""
        ws = self._sheet(SHEET_PARAMETERS)
        records = ws.get_all_records()
        rows = [i + 2 for i, r in enumerate(records)
                if str(r.get("話数", "")) == str(episode_number)]
        for idx in reversed(rows):
            ws.delete_rows(idx)
        print(f"DONE: Parameters削除: 第{episode_number}話 {len(rows)}行")
        return len(rows)

    def delete_episode_memory_l2(self, episode_number: int) -> int:
        """指定話数のL2記憶行をMemory_L2シートから削除する"""
        ws = self._sheet(SHEET_MEMORY_L2)
        records = ws.get_all_records()
        rows = [i + 2 for i, r in enumerate(records)
                if str(r.get("話数", "")) == str(episode_number)]
        for idx in reversed(rows):
            ws.delete_rows(idx)
        print(f"DONE: Memory_L2削除: 第{episode_number}話 {len(rows)}行")
        return len(rows)

    def build_past_cliffhangers_context(self) -> str:
        """過去全話のクリフハンガー一覧を返す（重複防止用、プロンプト埋め込み用）"""
        ws = self._sheet(SHEET_EPISODES)
        records = ws.get_all_records()
        if not records:
            return "過去のクリフハンガー: なし"
        lines = ["=== 使用済みクリフハンガー（絶対に同じ内容・パターンを繰り返さないこと） ==="]
        for ep in records:
            ep_num = ep.get("話数", "")
            ch = ep.get("クリフハンガー", "")
            if ch:
                lines.append(f"  第{ep_num}話: {ch}")
        return "\n".join(lines)

    def build_story_progress_context(self) -> str:
        """過去全話の目的・アプローチ一覧を返す（重複防止用、プロンプト埋め込み用）"""
        ws = self._sheet(SHEET_EPISODES)
        records = ws.get_all_records()
        if not records:
            return "ストーリー進行: まだ0話"
        lines = ["=== ストーリー進行状況（使用済みアプローチ一覧・繰り返し禁止） ==="]
        for ep in records:
            ep_num = ep.get("話数", "")
            title = ep.get("タイトル案", "")
            obj = ep.get("この話の目的", "")
            if ep_num:
                lines.append(f"  第{ep_num}話「{title}」: {obj}")
        return "\n".join(lines)

    def build_open_foreshadowing_context(self) -> str:
        """未回収の伏線一覧文字列を返す（プロンプト埋め込み用）"""
        items = self.get_open_foreshadowing()
        if not items:
            return "未回収の伏線はありません。"
        lines = ["=== 未回収の伏線リスト ==="]
        for item in items:
            lines.append(
                f"[{item.get('伏線ID', '???')}] ({item.get('重要度', 'MID')}) "
                f"第{item.get('追加話数', '')}話追加〜第{item.get('回収予定話数', '')}話回収予定: "
                f"{item.get('伏線内容', '')}"
            )
        return "\n".join(lines)

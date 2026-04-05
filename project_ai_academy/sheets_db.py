"""
sheets_db.py
Soul Reboot - Google Spreadsheet DB アクセス層
すべてのシートへの読み書きをこのモジュールで一元管理する。

認証方式: OAuth2（個人Googleアカウント）
  - 初回実行時: ブラウザが開いてGoogleアカウントでログイン
  - 2回目以降: token.json に認証情報がキャッシュされるため自動実行
  - 必要ファイル: credentials.json（Google Cloud ConsoleからDL）
"""

from collections import Counter

import gspread
from gspread.exceptions import WorksheetNotFound
from datetime import datetime, date
from typing import Optional
import os

from utils import safe_int as _safe_int, extract_video_id as _extract_video_id

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
SHEET_ANALYTICS     = "📈 Analytics"


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

        # 削除対象の行番号を収集（0-indexed で batchUpdate に渡す）
        rows_to_delete = [
            i + 1  # gspread は 1-indexed
            for i, row in enumerate(all_values[1:], start=1)
            if len(row) > ep_col_idx and row[ep_col_idx] == str(episode_number)
        ]
        if rows_to_delete:
            # 逆順にした deleteDimension リクエストを1回のバッチAPIコールで送信
            # → 個別 delete_rows() の繰り返しによる Write 429 を回避
            requests = [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "ROWS",
                            "startIndex": row_idx - 1,  # 0-indexed
                            "endIndex": row_idx,
                        }
                    }
                }
                for row_idx in sorted(rows_to_delete, reverse=True)
            ]
            ws.spreadsheet.batch_update({"requests": requests})
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
            line.setdefault("承認済", "TRUE")
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
        pending.sort(key=lambda x: _safe_int(x.get("採用スコア", 0)), reverse=True)
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
    # コンテキストビルダー（プロンプト埋め込み用テキスト生成）
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

    def get_recent_sentiments(self, limit: int = 50) -> list[str]:
        """直近N件のコメントのAI感情分析結果を返す"""
        try:
            ws = self._sheet(SHEET_COMMENTS)
            records = ws.get_all_records()
        except WorksheetNotFound:
            return []
        return [r.get("AI感情分析", "") for r in records[-limit:] if r.get("AI感情分析")]

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

    def build_past_structures_context(self) -> str:
        """過去全話の構造パターン・掛け合いパターン一覧を返す（重複防止用）"""
        ws = self._sheet(SHEET_EPISODES)
        records = ws.get_all_records()
        if not records:
            return "使用済み構造パターン: なし"
        lines = ["=== 使用済み構造パターン・掛け合いパターン（直近3話と同じパターンは避けること） ==="]
        for ep in records:
            ep_num = ep.get("話数", "")
            structure = ep.get("構造パターン", "")
            comedy = ep.get("掛け合いパターン", "")
            if ep_num and (structure or comedy):
                lines.append(f"  第{ep_num}話: 構造={structure or '未記録'} / 掛け合い={comedy or '未記録'}")
        return "\n".join(lines)

    def build_past_scene_settings_context(self) -> str:
        """過去全話のシーン舞台一覧を返す（舞台重複防止用）"""
        ws = self._sheet(SHEET_EPISODES)
        records = ws.get_all_records()
        if not records:
            return "使用済みシーン舞台: なし"
        lines = ["=== 使用済みシーン舞台（直近3話と同じメイン舞台は避けること） ==="]
        for ep in records:
            ep_num = ep.get("話数", "")
            scene_settings = ep.get("シーン舞台", "")
            if ep_num and scene_settings:
                lines.append(f"  第{ep_num}話: {scene_settings}")
        return "\n".join(lines)

    def build_dialogue_samples_context(self) -> str:
        """直近2話の代表的なセリフを返す（文体重複検知用）"""
        ws = self._sheet(SHEET_SCRIPTS)
        records = ws.get_all_records()
        if not records:
            return "直近のセリフサンプル: なし"

        # 話数でグルーピングし、直近2話を取得
        episodes = {}
        for r in records:
            ep = str(r.get("話数", ""))
            if ep:
                episodes.setdefault(ep, []).append(r)

        sorted_eps = sorted(episodes.keys(), key=lambda x: _safe_int(x), reverse=True)[:2]

        lines = ["=== 直近のセリフサンプル（同じ言い回し・文体の繰り返しを避けること） ==="]
        for ep_num in sorted_eps:
            ep_lines = episodes[ep_num]
            # ナギサとシンジのセリフから各3本ずつ抽出
            nagisa_lines = [r.get("セリフ・地の文", "") for r in ep_lines
                           if r.get("話者") == "NAGISA" and r.get("セリフ・地の文")][:3]
            shinji_lines = [r.get("セリフ・地の文", "") for r in ep_lines
                           if r.get("話者") == "SHINJI" and r.get("セリフ・地の文")][:3]
            lines.append(f"第{ep_num}話:")
            for s in nagisa_lines:
                lines.append(f"  ナギサ「{s[:60]}」")
            for s in shinji_lines:
                lines.append(f"  シンジ「{s[:60]}」")
        return "\n".join(lines)

    def get_parameter_targets(self, episode_number: int) -> dict:
        """ロードマップに基づくパラメータ目標レンジを返す（29話設計）"""
        targets = {
            (1,  9):  {"trust": (20, 50),  "awakening": (0,  0)},   # Day 01-09: 幸福な誤認
            (10, 21): {"trust": (50, 70),  "awakening": (0, 40)},   # Day 10-21: 魂のノイズ
            (22, 28): {"trust": (70, 100), "awakening": (40, 80)},  # Day 22-28: 聖域の崩壊
            (29, 29): {"trust": (0, 100),  "awakening": (0, 100)},  # Day 29: 終着点
        }
        for (start, end), target in targets.items():
            if start <= episode_number <= end:
                return target
        return {"trust": (0, 100), "awakening": (0, 100)}

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

    # -------------------------------------------------------------------
    # 📈 Analytics
    # -------------------------------------------------------------------

    def append_analytics(self, stats: list[dict]) -> None:
        """Analyticsシートに視聴統計を追記する"""
        try:
            ws = self._sheet(SHEET_ANALYTICS)
        except WorksheetNotFound:
            print(f"  [WARN] シート '{SHEET_ANALYTICS}' が見つかりません。スキップします。")
            return
        headers = ws.row_values(1)
        rows = []
        for s in stats:
            s.setdefault("収集日", date.today().isoformat())
            rows.append([str(s.get(h, "")) for h in headers])
        if rows:
            ws.append_rows(rows)
            print(f"DONE: Analytics追記: {len(rows)}件")

    def get_latest_analytics(self, limit: int = 5) -> list[dict]:
        """直近N話分の最新アナリティクスを返す（各話の最新収集日のみ）"""
        try:
            ws = self._sheet(SHEET_ANALYTICS)
        except WorksheetNotFound:
            print(f"  [WARN] シート '{SHEET_ANALYTICS}' が見つかりません。アナリティクスをスキップします。")
            return []
        records = ws.get_all_records()
        if not records:
            return []
        # 話数ごとに最新の収集日のレコードだけを残す
        latest = {}
        for r in records:
            ep = str(r.get("話数", ""))
            if ep and (ep not in latest or r.get("収集日", "") >= latest[ep].get("収集日", "")):
                latest[ep] = r
        # 話数の降順でソートし、limit件返す
        sorted_records = sorted(latest.values(), key=lambda x: _safe_int(x.get("話数", 0)), reverse=True)
        return sorted_records[:limit]

    def get_video_ids_for_recent_episodes(self, limit: int = 3) -> list[dict]:
        """YouTube_URLが設定されている直近N話の話数とvideo_idを返す"""
        ws = self._sheet(SHEET_EPISODES)
        records = ws.get_all_records()
        result = []
        for r in reversed(records):
            url = str(r.get("YouTube_URL", ""))
            if not url:
                continue
            video_id = _extract_video_id(url)
            if video_id:
                result.append({
                    "episode_number": _safe_int(r.get("話数", 0)),
                    "video_id": video_id,
                    "title": r.get("タイトル案", "") or r.get("確定タイトル", ""),
                })
            if len(result) >= limit:
                break
        return result

    def get_existing_comment_ids(self) -> set[str]:
        """Commentsシートに既に登録済みのコメントIDセットを返す（重複防止用）"""
        ws = self._sheet(SHEET_COMMENTS)
        records = ws.get_all_records()
        return {str(r.get("コメントID", "")) for r in records if r.get("コメントID")}

    def append_comments_batch(self, comments: list[dict]) -> int:
        """コメントを一括追加する（既存ID重複チェック済み前提）"""
        if not comments:
            return 0
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
            print(f"DONE: Comments一括追記: {len(rows)}件")
        return len(rows)

    def mark_comments_adopted(self, comment_ids: list[str]) -> None:
        """指定コメントIDの採用ステータスをADOPTEDに更新する"""
        if not comment_ids:
            return
        ws = self._sheet(SHEET_COMMENTS)
        all_values = ws.get_all_values()
        if not all_values:
            return
        headers = all_values[0]
        id_col = headers.index("コメントID") if "コメントID" in headers else -1
        status_col = headers.index("採用ステータス") if "採用ステータス" in headers else -1
        if id_col < 0 or status_col < 0:
            return
        id_set = set(comment_ids)
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > id_col and row[id_col] in id_set:
                ws.update_cell(i, status_col + 1, "ADOPTED")
        print(f"DONE: {len(comment_ids)}件のコメントをADOPTEDに更新")

    def build_analytics_context(self) -> str:
        """直近エピソードのアナリティクスサマリーを返す（Architectプロンプト埋め込み用）"""
        analytics = self.get_latest_analytics(limit=5)
        if not analytics:
            return "=== 視聴者データ ===\n  （まだデータがありません）"

        lines = ["=== 直近エピソードの視聴者反応 ==="]
        for a in analytics:
            ep = a.get("話数", "?")
            views = _safe_int(a.get("視聴回数", 0))
            likes = _safe_int(a.get("いいね数", 0))
            comments = _safe_int(a.get("コメント数", 0))
            engagement = float(a.get("エンゲージメント率", 0)) if a.get("エンゲージメント率") else 0
            lines.append(
                f"  第{ep}話: 視聴{views}回 / いいね{likes} / コメント{comments} / "
                f"エンゲージメント率{engagement:.1f}%"
            )

        # コメント傾向サマリー（最新50件の感情分析から）
        sentiments = self.get_recent_sentiments(limit=50)
        if sentiments:
            counts = Counter(sentiments)
            total = sum(counts.values())
            trend_parts = [f"{s}{c*100//total}%" for s, c in counts.most_common(4)]
            lines.append(f"  コメント傾向: {' / '.join(trend_parts)}")

        return "\n".join(lines)

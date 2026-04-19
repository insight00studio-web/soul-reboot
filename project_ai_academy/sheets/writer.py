"""sheets/writer.py - 書き込み系メソッド。

WriterMixin は SoulRebootDB に合成される。単独では使わない。
"""

from datetime import date, datetime

from gspread.exceptions import WorksheetNotFound

from utils import safe_int as _safe_int

from .schema import (
    SHEET_ANALYTICS,
    SHEET_ASSETS,
    SHEET_COMMENTS,
    SHEET_CONFIG,
    SHEET_EPISODES,
    SHEET_FORESHADOWING,
    SHEET_MEMORY_L2,
    SHEET_NEWS,
    SHEET_PARAMETERS,
    SHEET_SCRIPTS,
)


class WriterMixin:
    """書き込み系メソッドを担う Mixin。_sheet() と _config_cache 属性を前提とする。"""

    # -------------------------------------------------------------------
    # ⚙️ Config
    # -------------------------------------------------------------------

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

    def upsert_episode(self, data: dict) -> None:
        """
        Episodesシートに話のデータを書き込む。
        同じ「話数」の行が存在すれば更新、なければ追加。
        """
        ws = self._sheet(SHEET_EPISODES)
        ep_num = data["話数"]
        headers = ws.row_values(1)

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
        """台本の行データをまとめてScriptsシートに追記する。"""
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

    # -------------------------------------------------------------------
    # 📊 Parameters
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # 📖 Memory_L2
    # -------------------------------------------------------------------

    def append_memory_l2(self, episode_data: dict) -> None:
        """L2メモリに新しい話のサマリーを追記する"""
        ws = self._sheet(SHEET_MEMORY_L2)
        headers = ws.row_values(1)
        row = [str(episode_data.get(h, "")) for h in headers]
        ws.append_row(row)
        print(f"DONE: Memory_L2更新: 第{episode_data.get('話数')}話")

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

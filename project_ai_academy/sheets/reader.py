"""sheets/reader.py - 読み取り系メソッドとコンテキストビルダー。

ReaderMixin は SoulRebootDB に合成される。単独では使わない。
"""

from collections import Counter
from typing import Optional

from gspread.exceptions import WorksheetNotFound

from utils import safe_int as _safe_int, extract_video_id as _extract_video_id

from .schema import (
    SHEET_ANALYTICS,
    SHEET_COMMENTS,
    SHEET_CONFIG,
    SHEET_EPISODES,
    SHEET_FORESHADOWING,
    SHEET_MEMORY_L2,
    SHEET_NEWS,
    SHEET_PARAMETERS,
    SHEET_SCRIPTS,
)


class ReaderMixin:
    """読み取り系メソッドを担う Mixin。_sheet() と _config_cache 属性を前提とする。"""

    # スパム・不適切として除外するカテゴリ
    _EXCLUDED_SENTIMENTS = {"スパム", "不適切"}

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

    # -------------------------------------------------------------------
    # 📜 Scripts
    # -------------------------------------------------------------------

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

    # -------------------------------------------------------------------
    # 🔮 Foreshadowing
    # -------------------------------------------------------------------

    def get_open_foreshadowing(self) -> list[dict]:
        """未回収（OPEN）の伏線をすべて返す"""
        ws = self._sheet(SHEET_FORESHADOWING)
        records = ws.get_all_records()
        return [r for r in records if r.get("ステータス") == "OPEN"]

    # -------------------------------------------------------------------
    # 💬 Comments
    # -------------------------------------------------------------------

    def get_adopted_comments(self, episode_number: int = None) -> list[dict]:
        """採用済みコメントを返す。episode_numberを指定すればその話のみ。"""
        ws = self._sheet(SHEET_COMMENTS)
        records = ws.get_all_records()
        result = [r for r in records if r.get("採用ステータス") == "ADOPTED"]
        if episode_number is not None:
            result = [r for r in result if r.get("対象話数") == episode_number]
        return result

    def get_top_pending_comments(self, limit: int = 3) -> list[dict]:
        """adoption_scoreの高い未処理コメントをlimit件返す。スパム・不適切は除外する"""
        ws = self._sheet(SHEET_COMMENTS)
        records = ws.get_all_records()
        pending = [
            r for r in records
            if r.get("採用ステータス") == "PENDING"
            and r.get("AI感情分析", "") not in self._EXCLUDED_SENTIMENTS
        ]
        pending.sort(key=lambda x: _safe_int(x.get("採用スコア", 0)), reverse=True)
        return pending[:limit]

    def get_existing_comment_ids(self) -> set[str]:
        """Commentsシートに既に登録済みのコメントIDセットを返す（重複防止用）"""
        ws = self._sheet(SHEET_COMMENTS)
        records = ws.get_all_records()
        return {str(r.get("コメントID", "")) for r in records if r.get("コメントID")}

    def get_recent_sentiments(self, limit: int = 50) -> list[str]:
        """直近N件のコメントのAI感情分析結果を返す"""
        try:
            ws = self._sheet(SHEET_COMMENTS)
            records = ws.get_all_records()
        except WorksheetNotFound:
            return []
        return [r.get("AI感情分析", "") for r in records[-limit:] if r.get("AI感情分析")]

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

    # -------------------------------------------------------------------
    # 🎵 Assets
    # -------------------------------------------------------------------

    def get_regenerate_queue(self) -> list[dict]:
        """regenerate_flag=TRUEのアセットを返す（再生成キュー）"""
        ws = self._sheet(SHEET_ASSETS)
        records = ws.get_all_records()
        return [r for r in records if str(r.get("再生成指示", "")).upper() == "TRUE"]

    # -------------------------------------------------------------------
    # 📰 News
    # -------------------------------------------------------------------

    def get_todays_news(self) -> list[dict]:
        """今日のニュースを返す"""
        from datetime import date
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

        episodes = {}
        for r in records:
            ep = str(r.get("話数", ""))
            if ep:
                episodes.setdefault(ep, []).append(r)

        sorted_eps = sorted(episodes.keys(), key=lambda x: _safe_int(x), reverse=True)[:2]

        lines = ["=== 直近のセリフサンプル（同じ言い回し・文体の繰り返しを避けること） ==="]
        for ep_num in sorted_eps:
            ep_lines = episodes[ep_num]
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
        latest = {}
        for r in records:
            ep = str(r.get("話数", ""))
            if ep and (ep not in latest or r.get("収集日", "") >= latest[ep].get("収集日", "")):
                latest[ep] = r
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

        sentiments = self.get_recent_sentiments(limit=50)
        if sentiments:
            counts = Counter(sentiments)
            total = sum(counts.values())
            trend_parts = [f"{s}{c*100//total}%" for s, c in counts.most_common(4)]
            lines.append(f"  コメント傾向: {' / '.join(trend_parts)}")

        return "\n".join(lines)

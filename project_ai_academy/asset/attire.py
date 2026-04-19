"""asset/attire.py - 服装・物語内日付・場所推定のロジック。

AttireMixin は AssetGenerator に合成される。単独では使わない。
前提: self.weekend_attire が __init__ で設定されていること。
"""

from datetime import date, timedelta

from .constants import LOCATION_KEYWORD_MAP


class AttireMixin:
    """服装・物語内日付・場所キーの推定を担当する Mixin。"""

    # 学校内シーンを検出するキーワード（画像プロンプト内で使われる英語・日本語）
    SCHOOL_LOCATION_KEYWORDS = [
        "classroom", "library", "school", "hallway", "corridor", "rooftop",
        "shoe locker", "nurse office", "infirmary", "music room", "gym",
        "cafeteria", "auditorium", "laboratory", "teachers office",
        "教室", "図書室", "図書館", "廊下", "屋上", "下駄箱", "昇降口",
        "保健室", "音楽室", "体育館", "食堂", "講堂", "理科室", "職員室",
    ]

    def _get_nagisa_profile(self, awakening: int) -> str:
        """覚醒度に応じてナギサの声質プロファイルを返す"""
        if awakening <= 30:
            return "21歳の女子大学生。落ち着いた柔らかい声。やや冷静でクールなトーン。はっきりとした発音で語尾まで丁寧に読み上げる。エネルギーレベルは低め。"
        elif awakening <= 70:
            return "21歳の女子大学生。普段は落ち着いているが、ストレスで声がわずかに揺れる。冷静さの中に微かな不安が滲み出るトーン。語尾まで丁寧に読み上げる。"
        else:
            return "21歳の女子大学生。感情的に不安定な状態。声が震えて途切れがち。表面下に恐怖と混乱が感じられる。それでも語尾まで読み上げる。"

    def _get_story_date(self, ep_num: int):
        """エピソード番号から物語内日付を算出する（第1話=2026-04-08）"""
        return date(2026, 4, 8) + timedelta(days=ep_num - 1)

    def _get_attire_context(self, ep_num: int) -> str:
        """エピソード番号と画像プロンプトから服装コンテキストを返す。

        ルール:
          - 平日（月〜金） → 制服
          - 土日・祝日 → 季節に応じた私服（ep_numで1話内統一）

        ep_numから物語内日付を確定的に算出するため、同一エピソード内の
        全シーンで必ず同じ服装が選ばれる。
        """
        _NATIONAL_HOLIDAYS = {
            date(2026, 4, 29), date(2026, 5, 3), date(2026, 5, 4),
            date(2026, 5, 5), date(2026, 5, 6),
        }
        story_date = self._get_story_date(ep_num)
        weekday = story_date.weekday()  # 0=月曜, 6=日曜
        is_holiday = story_date in _NATIONAL_HOLIDAYS
        is_school_day = weekday < 5 and not is_holiday

        if is_school_day:
            return "school uniform, necktie, blazer"

        # 土日・祝日 → ep_numで候補リストから1種類を確定選択
        month = story_date.month
        candidates = self.weekend_attire.get(month, ["casual outfit"])
        attire = candidates[ep_num % len(candidates)]
        return attire

    def _get_emotional_overlay(self, awakening: int) -> str:
        """覚醒度に応じたビジュアルエフェクトタグを返す"""
        if awakening >= 71:
            return "heavy glitch, system error overlay, data fragment particles"
        elif awakening >= 31:
            return "slight chromatic aberration, subtle digital noise"
        return ""

    def _get_outfit_key(self, ep_num: int, img_prompt: str) -> str | None:
        """エピソードと画像プロンプトから適用する私服マスターキーを返す。制服の場合は None。"""
        attire = self._get_attire_context(ep_num)
        if "school uniform" in attire:
            return None
        # 室内/自宅
        if any(kw in img_prompt for kw in ["自宅", "リビング", "自室"]) or \
           any(kw in img_prompt.lower() for kw in ["home", "living room", "bedroom", "indoor"]):
            return "indoor"
        # お出かけ
        if any(kw in img_prompt for kw in ["デート", "お出かけ", "ショッピング"]) or \
           any(kw in img_prompt.lower() for kw in ["date", "shopping", "mall", "movie theater"]):
            return "outing"
        # 季節判定
        month = self._get_story_date(ep_num).month
        if month in (6, 7, 8):
            return "summer"
        if month in (11, 12, 1, 2, 3):
            return "winter"
        return "spring"

    def _extract_location_key(self, img_prompt: str) -> str:
        """画像プロンプトから場所を正規化して返す。不明な場合は空文字。"""
        prompt_lower = img_prompt.lower()
        for location_key, keywords in LOCATION_KEYWORD_MAP:
            for kw in keywords:
                if kw in img_prompt or kw in prompt_lower:
                    return location_key
        return ""

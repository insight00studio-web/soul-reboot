"""asset/orchestrator.py - AssetGenerator 本体と process_episode パイプライン。

AttireMixin / MasterMixin / TTSMixin / ImageMixin を合成した薄いファサード。
"""

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from sheets_db import SoulRebootDB

from .attire import AttireMixin
from .constants import MAX_RETRIES, OUTFIT_DEFINITIONS
from .image import ImageMixin
from .master import MasterMixin
from .tts import TTSMixin

# .envの読み込み
load_dotenv()


class AssetGenerator(AttireMixin, MasterMixin, TTSMixin, ImageMixin):
    """TTS・画像・サムネイル・エピソード処理をまとめたオーケストレータ。

    各領域のメソッドは Mixin に分割されている（asset/tts.py, asset/image.py ほか）。
    このクラスは初期化と process_episode のみを持つ。
    """

    def __init__(self, spreadsheet_id: str):
        self.db = SoulRebootDB(spreadsheet_id)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        # google-genai Client
        self.client = genai.Client(api_key=api_key)

        # 設定
        self.tts_model = "gemini-3.1-flash-tts-preview"
        self.image_model = "gemini-2.5-flash-image"

        self.voice_map = {
            "NAGISA": "Despina",
            "SHINJI": "Orus",
            "NARRATOR": "Charon",
            "SYSTEM": "Kore",
        }

        # キャラクターごとの詳細な属性定義（TTSプロンプト用）
        self.char_profiles = {
            "SHINJI": "16歳の男子高校生。明るく元気で温かみのある声。友好的で親しみやすいトーン。",
            "NARRATOR": "落ち着いた大人のナレーター。冷静でプロフェッショナルな語り口。",
            "SYSTEM": "落ち着いた大人のナレーター。冷静でプロフェッショナルな語り口。",
        }

        # 保存先ベースディレクトリ
        self.base_dir = Path(__file__).parent.parent
        self.assets_dir = self.base_dir / "assets"
        self.assets_dir.mkdir(exist_ok=True)

        # --- IMAGE GENERATION: キャラクター固定プロンプト ---
        self.char_image_base = {
            "NAGISA": "1girl, long black hair, sapphire blue eyes, long hair, beautiful detailed eyes, tsundere, upper body",
            "SHINJI": "1boy, messy brown hair, black eyes, soft expression, young male",
        }

        # --- IMAGE GENERATION: マスター参照画像パス ---
        self.master_image_paths = {
            "NAGISA": self.base_dir / "assets" / "masters" / "nagisa_master.png",
            "SHINJI": self.base_dir / "assets" / "masters" / "shinji_master.png",
        }

        # --- IMAGE GENERATION: マスター画像のメモリキャッシュ ---
        self._master_image_cache: dict = {}

        # --- IMAGE GENERATION: 私服マスター参照画像パス ---
        self.outfit_master_paths: dict[str, dict[str, Path]] = {
            char_key: {
                outfit_key: self.base_dir / "assets" / "masters" / f"{char_key.lower()}_casual_{outfit_key}.png"
                for outfit_key in OUTFIT_DEFINITIONS[char_key]
            }
            for char_key in OUTFIT_DEFINITIONS
        }

        # --- IMAGE GENERATION: 私服マスター画像のメモリキャッシュ ---
        self._outfit_master_cache: dict = {}

        # --- IMAGE GENERATION: サブキャラクター（シルエット表示用）---
        # img_prompt内に含まれる英語キーワード → シルエット説明の対応
        self.silhouette_chars = {
            "satomi": "adult woman in her 30s, glasses, neat black hair tied up, holding a small tablet",
            "homeroom teacher": "adult woman in her 30s, glasses, neat black hair tied up",
            "sakura": "teenage girl with short brown hair, cheerful",
            "ken": "teenage boy with short black hair, smiling",
            "shirakawa": "elderly woman in her 50s, white-streaked short hair, formal suit",
            "principal": "elderly woman in her 50s, white-streaked short hair, formal suit",
            "headmistress": "elderly woman in her 50s, white-streaked short hair, formal suit",
        }

        # --- IMAGE GENERATION: 週末服装（月別・複数候補） ---
        # ep_num で確定選択するため複数候補をリストで保持
        self.weekend_attire = {
            4: ["white blouse and cardigan", "light sweater and jeans", "casual coat and skirt"],
            5: ["thin blouse and pants", "casual dress", "shirt and light skirt"],
            6: ["short-sleeve shirt and shorts", "summer dress", "t-shirt and skirt"],
            7: ["summer dress", "t-shirt and shorts", "short-sleeve blouse and skirt"],
        }

    def _retry_on_429(self, exc: Exception, wait_seconds: int, attempt: int, label: str) -> bool:
        """レート制限例外なら待機してTrue、それ以外はエラーログしてFalseを返す"""
        if "429" in str(exc):
            print(f"    Rate limited. Waiting {wait_seconds}s (Attempt {attempt+1}/{MAX_RETRIES})...")
            time.sleep(wait_seconds)
            return True
        print(f"    ERROR: {label} failed: {exc}")
        return False

    def process_episode(self, ep_num: int, limit: int = None):
        """指定された話数のアセットを処理する"""
        gen_count = 0
        print(f"\n[PROCESS] Processing Episode {ep_num}...")

        # 承認済みスクリプトの取得
        scripts = self.db.get_approved_scripts(ep_num)
        if not scripts:
            print(f"  No approved scripts found for Episode {ep_num}. Skipping.")
            return

        print(f"  Found {len(scripts)} approved lines.")

        # 覚醒度パラメータを取得（感情オーバーレイ用）
        params = self.db.get_latest_parameters()
        awakening = int(params.get("覚醒度", 0))

        # 私服マスターの確認・自動生成
        self._ensure_outfit_masters()

        # シーンごとの画像プロンプトを追跡（同じシーンで重複生成しないため）
        processed_scenes = set()

        # 場所別 背景リファレンス画像キャッシュ（同一場所のシーン間で背景一貫性を保つため）
        location_bg_refs: dict[str, str] = {}

        # シーンごとの全話者を事前収集（NARRATORシーンでもキャラ登場を検出するため）
        scene_all_speakers: dict[int, list[str]] = {}
        for line in scripts:
            sn = int(line.get("シーン番号", 1))
            sp = line.get("話者", "")
            scene_all_speakers.setdefault(sn, [])
            if sp:
                scene_all_speakers[sn].append(sp)

        for line in scripts:
            if limit is not None and gen_count >= limit:
                print(f"  Reached limit of {limit} generations. Stopping.")
                break
            row_idx = line["_row_idx"]
            scene_num = int(line.get("シーン番号", 1))
            speaker = line.get("話者", "")
            text = line.get("セリフ・地の文", "")
            tone = line.get("感情トーン", "通常")
            img_prompt = line.get("画像プロンプト", "")

            # --- 画像生成 ---
            # シーンの最初の行に画像プロンプトがある場合のみ生成
            if img_prompt and scene_num not in processed_scenes:
                # シーン内の全話者を結合して渡す（NARRATOR話者でもキャラが映るシーンを正しく検出）
                all_speakers_in_scene = " ".join(scene_all_speakers.get(scene_num, [speaker]))
                location_key = self._extract_location_key(img_prompt)
                bg_reference = location_bg_refs.get(location_key) if location_key else None
                img_path = self.generate_image(
                    img_prompt, ep_num, scene_num,
                    speaker=all_speakers_in_scene, awakening=awakening,
                    bg_reference=bg_reference
                )
                if img_path:
                    if location_key and location_key not in location_bg_refs:
                        location_bg_refs[location_key] = img_path
                    self.db.register_asset(
                        episode_number=ep_num,
                        scene_number=scene_num,
                        asset_type="IMAGE",
                        file_path=img_path,
                        generation_prompt=img_prompt
                    )
                    processed_scenes.add(scene_num)

            # --- 音声生成 ---
            # パスが設定済みでもファイルが存在しない場合（別ランナー等）は再生成する
            existing_audio = line.get("音声ファイルパス")
            if not existing_audio or not os.path.exists(existing_audio):
                if speaker not in self.voice_map and speaker:
                    print(f"  [TTS] WARN: Unknown speaker '{speaker}'. Using default voice (Charon).")
                if speaker:
                    audio_path = self.generate_voice(speaker, text, tone, ep_num, row_idx)
                    if audio_path:
                        # Scriptsシートの更新
                        self.db.update_script_audio_path(row_idx, audio_path)
                        gen_count += 1
                        # Assetsシートの登録
                        self.db.register_asset(
                            episode_number=ep_num,
                            scene_number=scene_num,
                            asset_type=f"AUDIO_{speaker}",
                            file_path=audio_path,
                            generation_prompt=text
                        )


def main():
    parser = argparse.ArgumentParser(description="Soul Reboot アセット生成エンジン")
    parser.add_argument("--episode", type=int, help="処理する話数")
    parser.add_argument("--limit", type=int, help="生成する上限数")
    args = parser.parse_args()

    sid = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID")
    if not sid:
        print("ERROR: SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        return

    generator = AssetGenerator(sid)

    if args.episode:
        generator.process_episode(args.episode, limit=args.limit)
    else:
        # Configから現在の話数を取得して実行（または承認済みの全話 or 最新話）
        config = generator.db.get_config()
        current_ep = int(config.get("CURRENT_EPISODE", 1))
        # 通常、生成エンジンの後は current_ep が進んでいるので、その前の話数を処理する
        target_ep = current_ep - 1
        if target_ep >= 1:
            generator.process_episode(target_ep, limit=args.limit)
        else:
            print("No episode to process (CURRENT_EPISODE is 1)")


if __name__ == "__main__":
    main()

import os
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from sheets_db import SoulRebootDB

# .envの読み込み
load_dotenv()

import time

import wave

class AssetGenerator:
    def __init__(self, spreadsheet_id: str):
        self.db = SoulRebootDB(spreadsheet_id)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        # google-genai Client
        self.client = genai.Client(api_key=api_key)
        
        # 設定
        self.tts_model = "gemini-2.5-flash-preview-tts"
        self.image_model = "gemini-2.5-flash-image"
        
        self.voice_map = {
            "NAGISA": "Sulafat",
            "SHINJI": "Orus",
            "NARRATOR": "Charon",
            "SYSTEM": "Kore",
        }

        # キャラクターごとの詳細な属性定義（TTSプロンプト用）
        self.char_profiles = {
            "SHINJI": "16-year-old high school boy, energetic, warm, friendly voice",
            "NARRATOR": "Mature narrator, calm and professional narration",
            "SYSTEM": "Mechanical system voice, cold, robotic, authoritative",
        }
        
        # 保存先ベースディレクトリ
        self.base_dir = Path(__file__).parent
        self.assets_dir = self.base_dir / "assets"
        self.assets_dir.mkdir(exist_ok=True)

        # --- IMAGE GENERATION: キャラクター固定プロンプト ---
        self.char_image_base = {
            "NAGISA": "1girl, long black hair, sapphire blue eyes, long hair, beautiful detailed eyes, expressionless, kuudere, upper body",
            "SHINJI": "1boy, messy brown hair, black eyes, soft expression, young male",
        }

        # --- IMAGE GENERATION: マスター参照画像パス ---
        self.master_image_paths = {
            "NAGISA": self.base_dir / "assets" / "masters" / "nagisa_master.png",
            "SHINJI": self.base_dir / "assets" / "masters" / "shinji_master.png",
        }

        # --- IMAGE GENERATION: マスター画像のメモリキャッシュ ---
        self._master_image_cache: dict = {}

        # --- IMAGE GENERATION: 週末服装（月別） ---
        self.weekend_attire = {
            4: "cardigan, light coat, sweater",
            5: "blouse, thin shirt, dress",
            6: "short sleeves, summer dress, t-shirt",
            7: "short sleeves, summer dress, t-shirt",
        }

        # --- IMAGE GENERATION: ネガティブプロンプト（テキスト指示として埋め込む） ---
        self.negative_prompt_text = (
            "Avoid: multiple faces, extra limbs, deformed hands, blurry, low quality, "
            "watermark, text, different hairstyle than reference, different eye color than reference."
        )

    def _get_nagisa_profile(self, awakening: int) -> str:
        """覚醒度に応じてナギサの声質プロファイルを返す"""
        if awakening <= 30:
            return "16-year-old girl, composed, logical, cold, emotionless tone"
        elif awakening <= 70:
            return "16-year-old girl, normally composed but voice cracks slightly, uncertain"
        else:
            return "16-year-old girl, emotionally unstable, fearful, trembling voice"

    def _detect_characters(self, speaker: str, img_prompt: str) -> list:
        """speaker と img_prompt テキストから登場キャラクターを検出して返す"""
        detected = []
        combined = f"{speaker} {img_prompt}".upper()
        for char_key in self.char_image_base:
            if char_key in combined:
                detected.append(char_key)
        return detected

    def _get_attire_context(self) -> str:
        """公開日の曜日・月を取得し、服装・背景コンテキスト文字列を返す。

        公開日の算出:
          - 実行時刻 06:00 JST 以降 → 翌日06:00公開 → 翌日の曜日を使う
          - 実行時刻 00:00〜05:59 JST → 当日06:00公開 → 当日の曜日を使う
        """
        JST = timezone(timedelta(hours=9))
        now = datetime.now(JST)
        publish_date = now.date()
        if now.hour >= 6:
            publish_date = publish_date + timedelta(days=1)
        weekday = publish_date.weekday()  # 0=月曜, 6=日曜
        month = publish_date.month

        if weekday < 5:  # 平日（月〜金）→ 学校背景・制服
            return "school uniform, necktie, blazer"
        else:  # 土日・祝日 → 学校外・普段着
            attire = self.weekend_attire.get(month, "casual outfit")
            return attire

    def _get_emotional_overlay(self, awakening: int) -> str:
        """覚醒度に応じたビジュアルエフェクトタグを返す"""
        if awakening >= 71:
            return "heavy glitch, system error overlay, data fragment particles"
        elif awakening >= 31:
            return "slight chromatic aberration, subtle digital noise"
        return ""

    def _load_master_image_bytes(self, char_key: str):
        """マスター参照画像をディスクから読み込みキャッシュする。存在しない場合はNoneを返す"""
        if char_key in self._master_image_cache:
            return self._master_image_cache[char_key]

        img_path = self.master_image_paths.get(char_key)
        if img_path is None or not img_path.exists():
            print(f"  [IMAGE] WARN: Master image not found for {char_key}: {img_path}")
            return None

        with open(img_path, "rb") as f:
            data = f.read()

        self._master_image_cache[char_key] = data
        print(f"  [IMAGE] Loaded master image for {char_key} ({len(data)} bytes)")
        return data

    def build_image_prompt(self, img_prompt: str, speaker: str, awakening: int) -> str:
        """参照画像ベースの自然言語指示プロンプトを生成する"""
        characters = self._detect_characters(speaker, img_prompt)
        attire = self._get_attire_context()
        overlay = self._get_emotional_overlay(awakening)

        if characters:
            char_names = " and ".join(characters)
            parts = [
                f"Draw a new anime illustration scene featuring {char_names}.",
                "CRITICAL: The character(s) MUST look EXACTLY like in the reference image(s).",
                "Preserve without change: face shape, facial features, hair color, hair style, eye color, body proportions.",
                f"Scene: {img_prompt}",
                f"Attire and setting: {attire}",
            ]
            if overlay:
                parts.append(f"Visual effect: {overlay}")
            parts.append(
                "Style: anime illustration, same art style as reference image, "
                "high quality, sharp lines, vibrant colors."
            )
            parts.append(
                "Do NOT add: watermarks, text, extra limbs, deformed hands, "
                "multiple faces, or any deviation from the reference character design."
            )
        else:
            # NARRATORシーンなどキャラなし → テキストのみ
            parts = [
                f"Draw an anime-style background illustration: {img_prompt}",
                f"Setting: {attire}",
            ]
            if overlay:
                parts.append(f"Visual effect: {overlay}")
            parts.append("Style: anime illustration, cinematic, high quality, no characters.")

        return "\n".join(parts)

    def generate_voice(self, speaker: str, text: str, tone: str, ep_num: int, row_idx: int, awakening: int = 0) -> str:
        """Gemini-2.5-Flash-TTS を用いて音声を生成し、WAVヘッダーを付与して保存する"""
        voice_name = self.voice_map.get(speaker.upper(), "Charon")
        if speaker.upper() == "NAGISA":
            char_desc = self._get_nagisa_profile(awakening)
        else:
            char_desc = self.char_profiles.get(speaker.upper(), "Narrator")
        print(f"  [TTS] Generating voice for {speaker} (Voice: {voice_name}, Tone: {tone})...")
        
        # 詳細な指示プロンプトを構築
        full_prompt = (
            f"[Character: {speaker}, {char_desc}]\n"
            f"[Tone: {tone}]\n"
            f"Text: {text}"
        )

        for attempt in range(3):
            try:
                # TTSのリクエスト
                response = self.client.models.generate_content(
                    model=self.tts_model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name
                                )
                            )
                        )
                    )
                )
                
                # 音声データの取得
                audio_data = None
                mime_type = None
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        audio_data = part.inline_data.data
                        mime_type = part.inline_data.mime_type
                        break
                
                if not audio_data:
                    print("    ERROR: No audio data in response")
                    return ""
                
                # 保存
                ep_dir = self.assets_dir / "audio" / f"ep{ep_num:03d}"
                ep_dir.mkdir(parents=True, exist_ok=True)
                
                filename = f"ep{ep_num:03d}_{row_idx:04d}_{speaker}.wav"
                file_path = ep_dir / filename
                
                # MIMEタイプに応じて保存方法を変える
                # audio/L16 (PCM) の場合はWAVヘッダーが必要
                if "audio/L16" in mime_type or "codec=pcm" in mime_type:
                    # 24kHz, 16-bit, Mono と仮定（Gemini TTSの標準設定）
                    with wave.open(str(file_path), "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2) # 16-bit = 2 bytes
                        wav_file.setframerate(24000)
                        wav_file.writeframes(audio_data)
                else:
                    # それ以外（mp3など）はバイナリとしてそのまま保存
                    with open(file_path, "wb") as f:
                        f.write(audio_data)
                
                print(f"    Saved: {file_path}")
                time.sleep(21) # Rate limit回避
                return str(file_path)
                
            except Exception as e:
                if "429" in str(e):
                    print(f"    Rate limited. Waiting 30s (Attempt {attempt+1}/3)...")
                    time.sleep(35)
                    continue
                print(f"    ERROR: Voice generation failed: {e}")
                return ""
        return ""

    def generate_image(self, prompt: str, ep_num: int, scene_num: int, speaker: str = "", awakening: int = 0) -> str:
        """gemini-2.0-flash-exp を用いてキャラクター一貫性を保った画像を生成し保存する。

        マスター参照画像（PNG）+ 自然言語指示プロンプトのマルチモーダルリクエストを送信する。
        キャラクターなし（NARRATORのみ）のシーンはテキストプロンプトのみで生成する。
        """
        print(f"  [IMAGE] Generating image for Scene {scene_num}...")

        merged_prompt = self.build_image_prompt(prompt, speaker, awakening)
        characters = self._detect_characters(speaker, prompt)

        # マルチモーダルコンテンツを構築（マスター画像 → テキスト指示の順）
        contents = []
        for char_key in characters:
            img_bytes = self._load_master_image_bytes(char_key)
            if img_bytes is not None:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

        contents.append(merged_prompt)

        if not characters:
            print("  [IMAGE] No characters detected. Using text-only prompt.")
        elif len(contents) == 1:
            print("  [IMAGE] No master images loaded. Using text-only prompt.")

        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.image_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                        image_config=types.ImageConfig(
                            aspect_ratio="16:9",
                        ),
                    ),
                )
                
                image_data = None
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        image_data = part.inline_data.data
                        break
                
                if not image_data:
                    print("    ERROR: No image data in response")
                    return ""
                
                # 保存
                ep_dir = self.assets_dir / "images" / f"ep{ep_num:03d}"
                ep_dir.mkdir(parents=True, exist_ok=True)
                
                filename = f"ep{ep_num:03d}_sc{scene_num:02d}.png"
                file_path = ep_dir / filename
                
                with open(file_path, "wb") as f:
                    f.write(image_data)
                
                print(f"    Saved: {file_path}")
                time.sleep(21) # Rate limit回避
                return str(file_path)
                
            except Exception as e:
                if "429" in str(e):
                    print(f"    Rate limited. Waiting 60s (Attempt {attempt+1}/3)...")
                    time.sleep(65)
                    continue
                print(f"    ERROR: Image generation failed: {e}")
                return ""
        return ""

    # ------------------------------------------------------------------
    # サムネイル生成
    # ------------------------------------------------------------------

    def generate_thumbnail(self, ep_num: int, title: str, base_image_path: str) -> str:
        """シーン画像をベースにサムネイル画像を生成する（1280x720）"""
        THUMB_W, THUMB_H = 1280, 720

        if not os.path.exists(base_image_path):
            print(f"  WARN: ベース画像が見つかりません: {base_image_path}")
            return ""

        # フォント検索
        font_path = self._find_thumbnail_font()

        # 1. ベース画像読み込み → center-crop → 1280x720
        img = Image.open(base_image_path).convert("RGB")
        src_w, src_h = img.size
        target_ratio = THUMB_W / THUMB_H
        src_ratio = src_w / src_h

        if abs(src_ratio - target_ratio) > 0.01:
            if src_ratio > target_ratio:
                new_w = int(src_h * target_ratio)
                left = (src_w - new_w) // 2
                img = img.crop((left, 0, left + new_w, src_h))
            else:
                new_h = int(src_w / target_ratio)
                top = (src_h - new_h) // 2
                img = img.crop((0, top, src_w, top + new_h))

        img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)

        # 2. 下部グラデーション暗幕（下40%を徐々に暗く）
        overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        gradient_start = int(THUMB_H * 0.55)
        for y in range(gradient_start, THUMB_H):
            alpha = int(200 * (y - gradient_start) / (THUMB_H - gradient_start))
            overlay_draw.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))

        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)

        draw = ImageDraw.Draw(img)

        # 3. 話数テキスト（左上）
        ep_font = ImageFont.truetype(font_path, 80)
        ep_text = f"第{ep_num}話"
        self._draw_outlined_text(draw, (40, 24), ep_text, ep_font,
                                 fill=(255, 255, 255, 255), outline=(0, 0, 0, 255),
                                 outline_width=3)

        # 4. タイトルテキスト（下部中央）
        title_font = ImageFont.truetype(font_path, 56)
        max_title_w = int(THUMB_W * 0.85)
        # タイトルが長い場合は折り返し
        lines = self._wrap_thumbnail_text(title, title_font, max_title_w)

        y_pos = THUMB_H - 50 - len(lines) * 68
        for line in lines:
            bbox = title_font.getbbox(line)
            line_w = bbox[2] - bbox[0]
            x = (THUMB_W - line_w) // 2
            self._draw_outlined_text(draw, (x, y_pos), line, title_font,
                                     fill=(255, 255, 255, 255), outline=(0, 0, 0, 255),
                                     outline_width=3)
            y_pos += 68

        # 5. 保存
        thumb_dir = self.assets_dir / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"ep{ep_num:03d}_thumb.png"
        img = img.convert("RGB")
        img.save(str(thumb_path), "PNG")
        print(f"  [THUMBNAIL] Saved: {thumb_path}")
        return str(thumb_path)

    def _find_thumbnail_font(self) -> str:
        """サムネイル用日本語フォント（太字優先）"""
        candidates = [
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        raise FileNotFoundError("日本語フォントが見つかりません")

    @staticmethod
    def _draw_outlined_text(draw, pos, text, font, fill, outline, outline_width=3):
        """縁取り付きテキスト描画"""
        x, y = pos
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
        draw.text((x, y), text, font=font, fill=fill)

    @staticmethod
    def _wrap_thumbnail_text(text: str, font, max_width: int) -> list:
        """サムネイル用テキスト折り返し（最大2行）"""
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return [text]

        # 中央付近で分割
        mid = len(text) // 2
        best_pos = mid
        for offset in range(mid):
            for pos in [mid + offset, mid - offset]:
                if 0 < pos < len(text):
                    test = text[:pos]
                    tb = font.getbbox(test)
                    if (tb[2] - tb[0]) <= max_width:
                        best_pos = pos
                        break
            else:
                continue
            break

        line1 = text[:best_pos]
        line2 = text[best_pos:]
        # 2行目が長すぎる場合は省略
        tb2 = font.getbbox(line2)
        if (tb2[2] - tb2[0]) > max_width:
            result = ""
            for ch in line2:
                test = result + ch
                tb = font.getbbox(test)
                if (tb[2] - tb[0]) > max_width - font.getbbox("…")[2]:
                    line2 = result + "…"
                    break
                result = test
        return [line1, line2]

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

        # シーンごとの画像プロンプトを追跡（同じシーンで重複生成しないため）
        processed_scenes = set()

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
                # 既にAssetsシートに登録されているか確認（簡易。本来はSheetsDB側でチェックしたい）
                # ここでは常に生成して上書きor追加する（暫定）
                img_path = self.generate_image(img_prompt, ep_num, scene_num, speaker=speaker, awakening=awakening)
                if img_path:
                    self.db.register_asset(
                        episode_number=ep_num,
                        scene_number=scene_num,
                        asset_type="IMAGE",
                        file_path=img_path,
                        generation_prompt=img_prompt
                    )
                    processed_scenes.add(scene_num)

            # --- 音声生成 ---
            # 既に音声パスがある場合はスキップ
            if not line.get("音声ファイルパス"):
                if speaker and speaker in self.voice_map:
                    audio_path = self.generate_voice(speaker, text, tone, ep_num, row_idx, awakening=awakening)
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

"""asset/image.py - キャラクター一貫性を保った画像生成とサムネイル生成。

ImageMixin は AssetGenerator に合成される。単独では使わない。
前提: self.client, self.image_model, self.assets_dir, self.char_image_base,
     self.silhouette_chars, self._retry_on_429, self._detect_characters,
     self._detect_silhouette_chars, self.build_image_prompt,
     self._load_master_image_bytes, self._load_outfit_master_bytes,
     self._get_outfit_key, self._get_attire_context, self._get_emotional_overlay
     が利用可能であること。
"""

import os
import re
import time

from google.genai import types
from PIL import Image, ImageDraw, ImageFont

from utils import find_japanese_font

from .constants import (
    IMAGE_RETRY_WAIT_429,
    MAX_RETRIES,
    RATE_LIMIT_WAIT,
)


class ImageMixin:
    """画像・サムネイル生成を担当する Mixin。"""

    def _detect_characters(self, speaker: str, img_prompt: str) -> list:
        """speaker と img_prompt テキストから登場キャラクターを検出して返す"""
        detected = []
        combined = f"{speaker} {img_prompt}".upper()
        for char_key in self.char_image_base:
            if char_key in combined:
                detected.append(char_key)
        return detected

    def _detect_silhouette_chars(self, img_prompt: str) -> list[str]:
        """img_promptからサブキャラクターを検出してシルエット説明リストを返す"""
        detected = []
        prompt_lower = img_prompt.lower()
        seen = set()
        for keyword, description in self.silhouette_chars.items():
            if keyword in prompt_lower and description not in seen:
                detected.append(description)
                seen.add(description)
        return detected

    def build_image_prompt(self, img_prompt: str, speaker: str, awakening: int, ep_num: int = 1) -> str:
        """参照画像ベースの自然言語指示プロンプトを生成する"""
        characters = self._detect_characters(speaker, img_prompt)
        attire = self._get_attire_context(ep_num)
        overlay = self._get_emotional_overlay(awakening)

        if characters:
            char_names = " and ".join(characters)

            # --- サブキャラクターのシルエット処理 ---
            # メインキャラが存在するシーンでも、サブキャラ名がプロンプトに
            # 含まれている場合はキーワードを除去しシルエット指示を追加する
            silhouette_descs = self._detect_silhouette_chars(img_prompt)
            sanitized_prompt = img_prompt
            if silhouette_descs:
                for keyword in self.silhouette_chars:
                    sanitized_prompt = re.sub(
                        rf'\b{re.escape(keyword)}\b',
                        '',
                        sanitized_prompt,
                        flags=re.IGNORECASE,
                    )
                # 連続スペースを整理
                sanitized_prompt = re.sub(r'  +', ' ', sanitized_prompt).strip()

            parts = [
                f"Draw a new anime illustration scene featuring {char_names}.",
                "CRITICAL: The character(s) MUST look EXACTLY like in the reference image(s).",
                "Preserve without change: face shape, facial features, hair color, hair style, eye color, body proportions.",
                f"Scene: {sanitized_prompt}",
                f"Attire and setting: {attire}",
            ]
            # サブキャラをシルエットとして追加
            for desc in silhouette_descs:
                parts.append(
                    f"Also include a background figure ({desc}) rendered as a completely dark silhouette: "
                    "solid black fill, no facial features visible, no color details, outline only."
                )
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
            silhouette_descs = self._detect_silhouette_chars(img_prompt)
            if silhouette_descs:
                # サブキャラクターがいるシーン → シルエットで表示
                parts = [
                    f"Draw an anime-style illustration: {img_prompt}",
                    f"Setting: {attire}",
                ]
                for desc in silhouette_descs:
                    parts.append(
                        f"Include a figure ({desc}) rendered as a completely dark silhouette: "
                        "solid black fill, no facial features visible, no color details, outline only."
                    )
                if overlay:
                    parts.append(f"Visual effect: {overlay}")
                parts.append(
                    "Style: anime illustration, cinematic, high quality. "
                    "Do NOT show NAGISA or SHINJI in this scene."
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

    def generate_image(self, prompt: str, ep_num: int, scene_num: int,
                       speaker: str = "", awakening: int = 0,
                       bg_reference: str | None = None) -> str:
        """キャラクター一貫性を保った画像を生成し保存する。

        マスター参照画像（PNG）+ 私服マスター（該当時）+ 背景リファレンス（同一場所2シーン目以降）
        + 自然言語指示プロンプトのマルチモーダルリクエストを送信する。
        """
        print(f"  [IMAGE] Generating image for Scene {scene_num}...")

        merged_prompt = self.build_image_prompt(prompt, speaker, awakening, ep_num)
        characters = self._detect_characters(speaker, prompt)

        # マルチモーダルコンテンツを構築
        # 順序: キャラマスター → 私服マスター（私服時） → 背景リファレンス → テキスト
        contents = []

        # キャラクターマスター画像
        for char_key in characters:
            img_bytes = self._load_master_image_bytes(char_key)
            if img_bytes is not None:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

        # 私服マスター画像（制服でない場合のみ）
        outfit_key = self._get_outfit_key(ep_num, prompt)
        if outfit_key and characters:
            for char_key in characters:
                outfit_bytes = self._load_outfit_master_bytes(char_key, outfit_key)
                if outfit_bytes is not None:
                    contents.append(types.Part.from_bytes(data=outfit_bytes, mime_type="image/png"))

        # 同一場所の背景リファレンス画像（2シーン目以降）
        if bg_reference and os.path.exists(bg_reference):
            with open(bg_reference, "rb") as f:
                bg_bytes = f.read()
            contents.append(types.Part.from_bytes(data=bg_bytes, mime_type="image/png"))
            merged_prompt += (
                "\nIMPORTANT: Keep the background and environment CONSISTENT with the "
                "reference scene image provided. Same location, same lighting, same props and decorations."
            )

        contents.append(merged_prompt)

        if not characters:
            print("  [IMAGE] No characters detected. Using text-only prompt.")
        elif len(contents) == 1:
            print("  [IMAGE] No master images loaded. Using text-only prompt.")

        for attempt in range(MAX_RETRIES):
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
                time.sleep(RATE_LIMIT_WAIT)
                return str(file_path)

            except Exception as e:
                if self._retry_on_429(e, IMAGE_RETRY_WAIT_429, attempt, "Image generation"):
                    continue
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
        font_path = find_japanese_font()

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

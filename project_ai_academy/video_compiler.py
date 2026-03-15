"""
Soul Reboot - 動画コンパイラ
音声(WAV)＋画像(PNG)を合成してYouTube用MP4動画を書き出す。
"""

import os
import sys
import wave
import argparse
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips, ColorClip
)
from sheets_db import SoulRebootDB

load_dotenv()


class VideoCompiler:
    """エピソード動画のコンパイラ"""

    def __init__(self, spreadsheet_id: str):
        self.db = SoulRebootDB(spreadsheet_id)
        self.base_dir = Path(__file__).parent
        self.assets_dir = self.base_dir / "assets"
        self.output_dir = self.base_dir / "videos"
        self.output_dir.mkdir(exist_ok=True)

        # 動画設定
        self.width = 1920
        self.height = 1080
        self.fps = 24
        self.fade_duration = 0.5
        self.title_duration = 5.0
        self.ending_duration = 8.0

        # 字幕設定
        self.font_path = self._find_japanese_font()
        self.subtitle_font_size = 42
        self.speaker_name_font_size = 32
        self.subtitle_margin_bottom = 80
        self.subtitle_bar_height = 120
        self.subtitle_bar_opacity = 160  # 0-255

        # キャラクター別字幕色
        self.speaker_colors = {
            "NAGISA":    (100, 180, 255),
            "SHINJI":    (255, 180, 100),
            "NARRATOR":  (255, 255, 255),
            "SYSTEM":    (255, 80, 80),
        }

        print(f"[VIDEO] Font: {self.font_path}")

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    def _find_japanese_font(self) -> str:
        """Windows上で利用可能な日本語フォントを検索"""
        candidates = [
            "C:/Windows/Fonts/YuGothB.ttc",
            "C:/Windows/Fonts/YuGothM.ttc",
            "C:/Windows/Fonts/msgothic.ttc",
            "C:/Windows/Fonts/meiryo.ttc",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        raise FileNotFoundError(
            "日本語フォントが見つかりません。Windows標準フォントが必要です。"
        )

    def _get_audio_duration(self, audio_path: str) -> float:
        """WAVファイルの再生時間（秒）を返す。エラー時は0.0。"""
        try:
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate == 0:
                    return 0.0
                return frames / rate
        except Exception as e:
            print(f"  [VIDEO] WARN: 音声ファイル読み込みエラー: {audio_path} ({e})")
            return 0.0

    def _resolve_audio_path(self, raw_path: str) -> str | None:
        """スプレッドシートの音声パスを実ファイルパスに解決"""
        if not raw_path or not raw_path.strip():
            return None
        p = Path(raw_path)
        if p.is_absolute() and p.exists():
            return str(p)
        # 相対パスとして base_dir からの解決を試みる
        resolved = self.base_dir / raw_path
        if resolved.exists():
            return str(resolved)
        # assets/ 以下からの相対パスも試す
        resolved2 = self.assets_dir / raw_path
        if resolved2.exists():
            return str(resolved2)
        return None

    def _resolve_image_path(self, ep_num: int, scene_num: int) -> str | None:
        """シーン番号から画像ファイルパスを解決"""
        img_name = f"ep{ep_num:03d}_sc{scene_num:02d}.png"
        img_path = self.assets_dir / "images" / f"ep{ep_num:03d}" / img_name
        if img_path.exists():
            return str(img_path)
        return None

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont,
                   max_width: int) -> list[str]:
        """テキストを指定幅で最大2行に改行して行リストを返す。
        句読点・助詞の後など自然な位置で改行する。"""
        # 1行に収まる場合はそのまま
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return [text]

        # 自然な改行候補位置を探す（句読点・助詞の直後）
        break_chars = set("。、！？」）】》")
        post_particle = set("のはがをにでともへやらか")
        candidates = []
        for i, ch in enumerate(text):
            if i == 0 or i >= len(text) - 1:
                continue
            if ch in break_chars:
                candidates.append(i + 1)
            elif ch in post_particle and i + 1 < len(text) and text[i + 1] not in post_particle:
                candidates.append(i + 1)

        # テキスト中央付近の改行候補を優先
        mid = len(text) // 2
        best_pos = None
        best_dist = float("inf")
        for pos in candidates:
            dist = abs(pos - mid)
            if dist < best_dist:
                # 前半部分が max_width に収まるか確認
                front = text[:pos]
                fb = font.getbbox(front)
                if (fb[2] - fb[0]) <= max_width:
                    best_dist = dist
                    best_pos = pos

        if best_pos is not None:
            line1 = text[:best_pos]
            line2 = text[best_pos:]
            # 後半も収まるか確認、収まらなければ切り詰め
            lb = font.getbbox(line2)
            if (lb[2] - lb[0]) > max_width:
                line2 = self._truncate_to_width(line2, font, max_width)
            return [line1, line2]

        # 自然な改行位置が見つからない場合、文字幅ベースで分割
        line1 = ""
        for i, ch in enumerate(text):
            test = line1 + ch
            tb = font.getbbox(test)
            if (tb[2] - tb[0]) > max_width:
                break
            line1 = test
        line2 = text[len(line1):]
        if line2:
            lb = font.getbbox(line2)
            if (lb[2] - lb[0]) > max_width:
                line2 = self._truncate_to_width(line2, font, max_width)
            return [line1, line2]
        return [line1]

    def _truncate_to_width(self, text: str, font: ImageFont.FreeTypeFont,
                           max_width: int) -> str:
        """テキストを指定幅に収まるように末尾を切る"""
        result = ""
        for ch in text:
            test = result + ch
            tb = font.getbbox(test)
            if (tb[2] - tb[0]) > max_width:
                return result + "…"
            result = test
        return result

    # ------------------------------------------------------------------
    # 字幕画像生成
    # ------------------------------------------------------------------

    def _create_subtitle_image(self, text: str, speaker: str) -> np.ndarray:
        """字幕テキストをRGBA numpy配列として生成"""
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        font = ImageFont.truetype(self.font_path, self.subtitle_font_size)
        name_font = ImageFont.truetype(self.font_path, self.speaker_name_font_size)

        # 話者名のフォーマット
        speaker_color = self.speaker_colors.get(speaker, (255, 255, 255))
        if speaker in ("NARRATOR",):
            display_text = text
            speaker_label = ""
        elif speaker == "SYSTEM":
            display_text = text
            speaker_label = "SYSTEM: "
        else:
            char_name = {"NAGISA": "ナギサ", "SHINJI": "シンジ"}.get(speaker, speaker)
            display_text = text
            speaker_label = f"{char_name}："

        # テキスト折り返し
        usable_width = int(self.width * 0.85)
        wrapped = self._wrap_text(display_text, font, usable_width)

        # 行の高さ計算
        line_height = self.subtitle_font_size + 8
        total_text_height = len(wrapped) * line_height
        if speaker_label:
            total_text_height += self.speaker_name_font_size + 4

        # 半透明黒バーの描画
        bar_height = total_text_height + 40
        bar_top = self.height - self.subtitle_margin_bottom - bar_height
        bar_overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar_overlay)
        bar_draw.rectangle(
            [0, bar_top, self.width, bar_top + bar_height],
            fill=(0, 0, 0, self.subtitle_bar_opacity)
        )
        img = Image.alpha_composite(img, bar_overlay)
        draw = ImageDraw.Draw(img)

        # テキスト描画位置
        y = bar_top + 15

        # 話者名ラベル
        if speaker_label:
            label_bbox = name_font.getbbox(speaker_label)
            label_w = label_bbox[2] - label_bbox[0]
            label_x = (self.width - usable_width) // 2
            # 黒縁取り
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((label_x + dx, y + dy), speaker_label,
                              font=name_font, fill=(0, 0, 0, 255))
            draw.text((label_x, y), speaker_label,
                      font=name_font, fill=(*speaker_color, 255))
            y += self.speaker_name_font_size + 4

        # セリフ本文
        for line in wrapped:
            line_bbox = font.getbbox(line)
            line_w = line_bbox[2] - line_bbox[0]
            x = (self.width - line_w) // 2
            # 黒縁取り
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), line,
                              font=font, fill=(0, 0, 0, 255))
            draw.text((x, y), line, font=font, fill=(*speaker_color, 255))
            y += line_height

        return np.array(img)

    # ------------------------------------------------------------------
    # クリップ生成
    # ------------------------------------------------------------------

    def _create_scene_clip(self, image_path: str | None, audio_path: str | None,
                           text: str, speaker: str) -> CompositeVideoClip:
        """1行分のシーンクリップを生成"""
        # 画像
        if image_path and os.path.exists(image_path):
            pil_img = Image.open(image_path).convert("RGB")
            # アスペクト比を保持してリサイズ（中央クロップ）
            src_w, src_h = pil_img.size
            target_ratio = self.width / self.height  # 16:9
            src_ratio = src_w / src_h
            if abs(src_ratio - target_ratio) > 0.01:
                # アスペクト比が異なる場合、中央クロップ
                if src_ratio > target_ratio:
                    # 横長すぎ → 左右を切る
                    new_w = int(src_h * target_ratio)
                    left = (src_w - new_w) // 2
                    pil_img = pil_img.crop((left, 0, left + new_w, src_h))
                else:
                    # 縦長すぎ → 上下を切る
                    new_h = int(src_w / target_ratio)
                    top = (src_h - new_h) // 2
                    pil_img = pil_img.crop((0, top, src_w, top + new_h))
            pil_img = pil_img.resize((self.width, self.height), Image.LANCZOS)
            bg_array = np.array(pil_img)
        else:
            bg_array = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # 音声と再生時間
        if audio_path and os.path.exists(audio_path):
            duration = self._get_audio_duration(audio_path) + 0.3
            audio_clip = AudioFileClip(audio_path)
        else:
            duration = max(len(text) / 4, 2.0)
            audio_clip = None

        # ベース画像クリップ
        bg_clip = ImageClip(bg_array).set_duration(duration)

        # 字幕オーバーレイ
        subtitle_array = self._create_subtitle_image(text, speaker)
        subtitle_clip = ImageClip(subtitle_array, ismask=False).set_duration(duration)

        # 合成
        composite = CompositeVideoClip([bg_clip, subtitle_clip],
                                       size=(self.width, self.height))
        if audio_clip:
            composite = composite.set_audio(audio_clip)

        return composite

    def _create_title_card(self, ep_num: int, title: str) -> ImageClip:
        """タイトルカードを生成（5秒）"""
        img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 話数（大きめ）
        ep_font = ImageFont.truetype(self.font_path, 72)
        ep_text = f"第{ep_num}話"
        ep_bbox = ep_font.getbbox(ep_text)
        ep_w = ep_bbox[2] - ep_bbox[0]
        draw.text(((self.width - ep_w) // 2, 380), ep_text,
                  font=ep_font, fill=(255, 255, 255))

        # タイトル
        title_font = ImageFont.truetype(self.font_path, 48)
        # 長いタイトルは折り返し
        wrapped = self._wrap_text(title, title_font, int(self.width * 0.8))
        y = 500
        for line in wrapped:
            line_bbox = title_font.getbbox(line)
            line_w = line_bbox[2] - line_bbox[0]
            draw.text(((self.width - line_w) // 2, y), line,
                      font=title_font, fill=(200, 200, 200))
            y += 60

        clip = ImageClip(np.array(img)).set_duration(self.title_duration)
        return clip.fadein(0.5)

    def _create_ending_card(self, ep_num: int, cliffhanger: str) -> ImageClip:
        """エンディングカードを生成（8秒）"""
        img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        font = ImageFont.truetype(self.font_path, 40)
        small_font = ImageFont.truetype(self.font_path, 32)

        # 次回予告
        if cliffhanger:
            next_text = f"次回、第{ep_num + 1}話へ続く..."
            next_bbox = font.getbbox(next_text)
            next_w = next_bbox[2] - next_bbox[0]
            draw.text(((self.width - next_w) // 2, 350), next_text,
                      font=font, fill=(255, 255, 255))

            # クリフハンガーテキスト
            wrapped = self._wrap_text(cliffhanger, small_font, int(self.width * 0.75))
            y = 430
            for line in wrapped:
                line_bbox = small_font.getbbox(line)
                line_w = line_bbox[2] - line_bbox[0]
                draw.text(((self.width - line_w) // 2, y), line,
                          font=small_font, fill=(180, 180, 180))
                y += 44

        # コメント誘導
        cta_text = "あなたはどう思いますか？コメントで教えてください"
        cta_font = ImageFont.truetype(self.font_path, 36)
        cta_bbox = cta_font.getbbox(cta_text)
        cta_w = cta_bbox[2] - cta_bbox[0]
        draw.text(((self.width - cta_w) // 2, 700), cta_text,
                  font=cta_font, fill=(150, 200, 255))

        clip = ImageClip(np.array(img)).set_duration(self.ending_duration)
        return clip.fadeout(1.0)

    # ------------------------------------------------------------------
    # 覚醒度エフェクト
    # ------------------------------------------------------------------

    def _apply_awakening_effects(self, clip, awakening: int):
        """覚醒度に応じたビジュアルエフェクトを適用"""
        if awakening < 31:
            return clip

        def add_noise(get_frame, t):
            frame = get_frame(t)
            if awakening >= 71:
                # グリッチ効果（ランダムな行をシフト）
                result = frame.copy()
                if np.random.random() < 0.1:
                    h = frame.shape[0]
                    start = np.random.randint(0, h - 50)
                    end = min(start + np.random.randint(10, 50), h)
                    shift = np.random.randint(-30, 30)
                    result[start:end] = np.roll(frame[start:end], shift, axis=1)
                noise = np.random.normal(0, 8, frame.shape).astype(np.int16)
                result = np.clip(result.astype(np.int16) + noise, 0, 255).astype(np.uint8)
                return result
            else:
                # 軽度ノイズ
                noise = np.random.normal(0, 4, frame.shape).astype(np.int16)
                result = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
                return result

        return clip.fl(add_noise)

    # ------------------------------------------------------------------
    # メイン処理
    # ------------------------------------------------------------------

    def compile_episode(self, ep_num: int) -> str:
        """エピソード動画をコンパイルする"""
        print(f"\n[VIDEO] Processing Episode {ep_num}...")

        # データ取得
        scripts = self.db.get_approved_scripts(ep_num)
        if not scripts:
            print(f"  [VIDEO] ERROR: 承認済みスクリプトが見つかりません (Episode {ep_num})")
            sys.exit(1)

        episode_data = self.db.get_episode(ep_num)
        title = episode_data.get("タイトル案", f"第{ep_num}話") if episode_data else f"第{ep_num}話"
        cliffhanger = episode_data.get("クリフハンガー", "") if episode_data else ""

        params = self.db.get_latest_parameters()
        awakening = int(params.get("覚醒度", 0))

        print(f"  Found {len(scripts)} approved lines.")
        print(f"  Title: {title}")
        print(f"  Awakening: {awakening}")

        clips = []

        # --- タイトルカード ---
        print("  [VIDEO] Creating title card...")
        title_clip = self._create_title_card(ep_num, title)
        clips.append(title_clip)

        # --- シーンクリップ ---
        prev_scene = None
        for i, line in enumerate(scripts):
            scene_num = int(line.get("シーン番号", 0))
            speaker = str(line.get("話者", "NARRATOR"))
            text = str(line.get("セリフ・地の文", ""))
            audio_raw = str(line.get("音声ファイルパス", ""))

            if not text.strip():
                continue

            # パス解決
            audio_path = self._resolve_audio_path(audio_raw)
            image_path = self._resolve_image_path(ep_num, scene_num)

            if not audio_path:
                print(f"  [VIDEO] WARN: 音声欠落 (行{i+1}, {speaker})")
            if not image_path and scene_num != prev_scene:
                print(f"  [VIDEO] WARN: 画像欠落 (Scene {scene_num})")

            print(f"  [VIDEO] Scene {scene_num}, {speaker}: {text[:20]}...")

            clip = self._create_scene_clip(image_path, audio_path, text, speaker)

            # シーン切替時にフェード
            if prev_scene is not None and scene_num != prev_scene:
                clip = clip.fadein(self.fade_duration)
                if clips:
                    clips[-1] = clips[-1].fadeout(self.fade_duration)

            clips.append(clip)
            prev_scene = scene_num

        # --- エンディングカード ---
        print("  [VIDEO] Creating ending card...")
        if clips:
            clips[-1] = clips[-1].fadeout(self.fade_duration)
        ending_clip = self._create_ending_card(ep_num, cliffhanger)
        clips.append(ending_clip)

        # --- 結合 ---
        print("  [VIDEO] Concatenating clips...")
        final = concatenate_videoclips(clips, method="compose")

        # --- 覚醒度エフェクト ---
        if awakening >= 31:
            print(f"  [VIDEO] Applying awakening effects (level={awakening})...")
            final = self._apply_awakening_effects(final, awakening)

        # --- 書き出し ---
        output_path = str(self.output_dir / f"ep{ep_num:03d}.mp4")
        print(f"  [VIDEO] Writing to {output_path}...")
        final.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            bitrate="5000k",
            threads=4,
            logger="bar",
        )

        # --- クリーンアップ ---
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        final.close()

        # --- Assetsシート登録 ---
        try:
            self.db.register_asset(
                episode_number=ep_num,
                scene_number=0,
                asset_type="VIDEO",
                file_path=output_path,
                generation_prompt=f"Episode {ep_num} compiled video"
            )
            print(f"DONE: Asset登録完了: EP{ep_num:03d}-SC00-VIDEO")
        except Exception as e:
            print(f"  [VIDEO] WARN: Asset登録エラー: {e}")

        print(f"\n[VIDEO] Episode {ep_num} 完了: {output_path}")
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Soul Reboot 動画コンパイラ")
    parser.add_argument("--episode", type=int, help="処理する話数")
    args = parser.parse_args()

    sid = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID")
    if not sid:
        print("ERROR: SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        return

    compiler = VideoCompiler(sid)

    if args.episode:
        compiler.compile_episode(args.episode)
    else:
        config = compiler.db.get_config()
        current_ep = int(config.get("CURRENT_EPISODE", 1))
        target_ep = current_ep - 1
        if target_ep >= 1:
            compiler.compile_episode(target_ep)
        else:
            print("No episode to compile (CURRENT_EPISODE is 1)")


if __name__ == "__main__":
    main()

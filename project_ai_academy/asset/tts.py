"""asset/tts.py - Gemini TTS による音声生成。

TTSMixin は AssetGenerator に合成される。単独では使わない。
前提: self.client, self.tts_model, self.voice_map, self.assets_dir,
     self._retry_on_429 が利用可能であること。
"""

import time
import wave
from collections import Counter

from google.genai import types

from .audio_split import split_wav_by_silence, write_wav_segment
from .constants import (
    CHAR_STYLE_PREFIX,
    MAX_RETRIES,
    RATE_LIMIT_WAIT,
    SILENCE_MIN_SEC,
    SILENCE_THRESHOLD_DB,
    TONE_TAG_MAP,
    TTS_RETRY_WAIT_429,
)


class TTSMixin:
    """TTS 音声生成を担当する Mixin。"""

    def generate_voice(self, speaker: str, text: str, tone: str, ep_num: int, row_idx: int) -> str:
        """Gemini-3.1-Flash-TTS を用いて音声を生成し、WAVヘッダーを付与して保存する"""
        voice_name = self.voice_map.get(speaker.upper(), "Charon")
        print(f"  [TTS] Generating voice for {speaker} (Voice: {voice_name}, Tone: {tone})...")

        # Gemini TTS は contents に渡した文字列をそのまま読み上げる。
        # キャラスタイル + 感情トーンを組み合わせた自然言語プレフィックスで制御する。
        emotion_tag = TONE_TAG_MAP.get(tone, "")
        style = CHAR_STYLE_PREFIX.get(speaker.upper(), "")
        speaker_upper = speaker.upper()

        if speaker_upper in ("NARRATOR", "SYSTEM"):
            # ナレーター・システムは感情タグを無視して常に冷静な語り口
            full_prompt = f"{style} Narrate: {text}" if style else text
        elif style and emotion_tag:
            full_prompt = f"{style} Deliver with a {emotion_tag} tone: {text}"
        elif style:
            full_prompt = f"{style} Say naturally: {text}"
        elif emotion_tag:
            full_prompt = f"Deliver with a {emotion_tag} tone: {text}"
        else:
            full_prompt = text

        for attempt in range(MAX_RETRIES):
            try:
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

                # レスポンスの妥当性チェック（Noneや空candidatesはリトライ）
                if response is None or not response.candidates:
                    print(f"    WARN: Empty response (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue
                content_obj = response.candidates[0].content
                if content_obj is None or not content_obj.parts:
                    print(f"    WARN: No content in response (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue

                # 音声データの取得
                audio_data = None
                mime_type = None
                for part in content_obj.parts:
                    if part.inline_data:
                        audio_data = part.inline_data.data
                        mime_type = part.inline_data.mime_type
                        break

                if not audio_data:
                    print(f"    WARN: No audio data in response (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue

                # 保存
                ep_dir = self.assets_dir / "audio" / f"ep{ep_num:03d}"
                ep_dir.mkdir(parents=True, exist_ok=True)

                filename = f"ep{ep_num:03d}_{row_idx:04d}_{speaker}.wav"
                file_path = ep_dir / filename

                # RIFFヘッダーの有無でWAV済みか生PCMかを判定
                # MIMEタイプはAPIバージョンによって変わるため信頼しない
                print(f"    MIME: {mime_type}, size: {len(audio_data)} bytes")
                if audio_data[:4] == b'RIFF':
                    with open(file_path, "wb") as f:
                        f.write(audio_data)
                else:
                    # 生PCMデータ → 24kHz/16-bit/Mono でWAVヘッダーを付与
                    with wave.open(str(file_path), "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(24000)
                        wav_file.writeframes(audio_data)

                print(f"    Saved: {file_path}")
                time.sleep(RATE_LIMIT_WAIT)
                return str(file_path)

            except Exception as e:
                if self._retry_on_429(e, TTS_RETRY_WAIT_429, attempt, "Voice generation"):
                    continue
                return ""
        return ""

    def generate_voice_batch_dialog(
        self,
        turns: list[dict],
        ep_num: int,
        scene_num: int,
        row_idxs: list[int],
    ) -> list[str] | None:
        """マルチスピーカー TTS で1コール生成 → 無音検出で行ごと WAV に分割。

        turns: [{"speaker": str, "text": str, "tone": str}, ...]
        return: row_idxs と同じ長さの per-line WAV パスリスト。
                マルチスピーカー生成または分割に失敗した場合は None。
        """
        assert len(turns) == len(row_idxs)
        speakers_in_order = [t["speaker"].upper() for t in turns]
        unique_speakers = list(dict.fromkeys(speakers_in_order))
        if len(unique_speakers) > 2:
            return None  # multi-speaker は最大2話者

        # 行ごとに感情ヒントを埋め込み、より自然なダイアログ演技を促す
        dialog_lines = []
        for t in turns:
            line_emotion = TONE_TAG_MAP.get(t.get("tone", ""), "")
            sp_label = t["speaker"].upper()
            if line_emotion:
                dialog_lines.append(f"{sp_label} [{line_emotion}]: {t['text']}")
            else:
                dialog_lines.append(f"{sp_label}: {t['text']}")
        dialog_body = "\n".join(dialog_lines)
        full_prompt = f"Perform this natural dialog. Each speaker should sound distinct and not over-act:\n{dialog_body}"

        # dominant_tone は printログ用に保持
        dominant_tone, _ = Counter(t.get("tone", "") for t in turns).most_common(1)[0]

        speaker_voice_configs = [
            types.SpeakerVoiceConfig(
                speaker=sp,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_map.get(sp, "Charon")
                    )
                ),
            )
            for sp in unique_speakers
        ]

        print(
            f"  [TTS-BATCH] Scene {scene_num}: {len(turns)} turns, "
            f"speakers={unique_speakers}, tone={dominant_tone or 'none'}"
        )

        audio_data = None
        mime_type = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.tts_model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                                speaker_voice_configs=speaker_voice_configs
                            )
                        ),
                    ),
                )
                if response is None or not response.candidates:
                    print(f"    WARN: Empty response (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue
                content_obj = response.candidates[0].content
                if content_obj is None or not content_obj.parts:
                    print(f"    WARN: No content in response (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue
                for part in content_obj.parts:
                    if part.inline_data:
                        audio_data = part.inline_data.data
                        mime_type = part.inline_data.mime_type
                        break
                if audio_data:
                    break
                print(f"    WARN: No audio data (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                time.sleep(TTS_RETRY_WAIT_429)
            except Exception as e:
                if self._retry_on_429(e, TTS_RETRY_WAIT_429, attempt, "Batch voice generation"):
                    continue
                return None

        if not audio_data:
            return None

        batch_path = self.assets_dir / "audio" / f"ep{ep_num:03d}" / f"ep{ep_num:03d}_sc{scene_num:02d}_batch.wav"
        return self._save_and_split_batch_wav(audio_data, mime_type, batch_path, turns, row_idxs, ep_num)

    def _save_and_split_batch_wav(
        self,
        audio_data: bytes,
        mime_type: str,
        batch_path,
        turns: list[dict],
        row_idxs: list[int],
        ep_num: int,
    ) -> list[str] | None:
        """バッチ生成した音声データをWAV保存→無音分割→行ごとファイル書き出し。"""
        ep_dir = batch_path.parent
        ep_dir.mkdir(parents=True, exist_ok=True)

        print(f"    MIME: {mime_type}, size: {len(audio_data)} bytes")
        if audio_data[:4] == b'RIFF':
            with open(batch_path, "wb") as f:
                f.write(audio_data)
        else:
            with wave.open(str(batch_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(audio_data)

        boundaries = split_wav_by_silence(
            str(batch_path),
            expected_count=len(turns),
            min_silence_sec=SILENCE_MIN_SEC,
            threshold_db=SILENCE_THRESHOLD_DB,
        )
        if boundaries is None:
            print(
                f"    WARN: Silence-based split mismatch "
                f"(expected {len(turns)} segments). Falling back to per-line generation."
            )
            time.sleep(RATE_LIMIT_WAIT)
            return None

        out_paths: list[str] = []
        for turn, row_idx, (start_s, end_s) in zip(turns, row_idxs, boundaries):
            speaker = turn["speaker"].upper()
            filename = f"ep{ep_num:03d}_{row_idx:04d}_{speaker}.wav"
            seg_path = ep_dir / filename
            write_wav_segment(str(batch_path), str(seg_path), start_s, end_s)
            print(f"    Saved segment: {seg_path} ({end_s - start_s:.2f}s)")
            out_paths.append(str(seg_path))

        time.sleep(RATE_LIMIT_WAIT)
        return out_paths

    def generate_voice_batch_monologue(
        self,
        turns: list[dict],
        ep_num: int,
        scene_num: int,
        row_idxs: list[int],
    ) -> list[str] | None:
        """単話者バッチTTS: 同一シーン内の連続行を1コールで生成→無音分割。

        turns: [{"speaker": str, "text": str, "tone": str}, ...]  (全て同一話者)
        return: row_idxs と同じ長さの per-line WAV パスリスト。失敗時は None。
        """
        assert len(turns) == len(row_idxs)
        speaker = turns[0]["speaker"].upper()
        voice_name = self.voice_map.get(speaker, "Charon")
        style = CHAR_STYLE_PREFIX.get(speaker, "")

        # 各行を段落として連結（文末の間でsplit_wav_by_silenceが分割できる）
        lines_text = "\n\n".join(t["text"] for t in turns)
        full_prompt = (
            f"{style} Narrate each passage clearly, with a distinct pause between them:"
            f"\n\n{lines_text}"
        )

        print(f"  [TTS-MONO] Scene {scene_num}: {len(turns)} lines, speaker={speaker}")

        audio_data = None
        mime_type = None
        for attempt in range(MAX_RETRIES):
            try:
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
                        ),
                    ),
                )
                if response is None or not response.candidates:
                    print(f"    WARN: Empty response (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue
                content_obj = response.candidates[0].content
                if content_obj is None or not content_obj.parts:
                    print(f"    WARN: No content (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                    time.sleep(TTS_RETRY_WAIT_429)
                    continue
                for part in content_obj.parts:
                    if part.inline_data:
                        audio_data = part.inline_data.data
                        mime_type = part.inline_data.mime_type
                        break
                if audio_data:
                    break
                print(f"    WARN: No audio data (Attempt {attempt+1}/{MAX_RETRIES}). Retrying...")
                time.sleep(TTS_RETRY_WAIT_429)
            except Exception as e:
                if self._retry_on_429(e, TTS_RETRY_WAIT_429, attempt, "Mono voice generation"):
                    continue
                return None

        if not audio_data:
            return None

        batch_path = (
            self.assets_dir / "audio" / f"ep{ep_num:03d}"
            / f"ep{ep_num:03d}_sc{scene_num:02d}_{speaker.lower()}_mono.wav"
        )
        return self._save_and_split_batch_wav(audio_data, mime_type, batch_path, turns, row_idxs, ep_num)

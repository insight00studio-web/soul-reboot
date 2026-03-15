# Asset Generator 設計構想 (Gemini-2.5-Flash-TTS版)

## 1. 目的

`autonomous_engine.py` で生成された台本（Scriptsシート）に基づき、Gemini-2.5-Flash-TTS (Speech Generation) を用いて音声を生成し、画像生成AI等のアセット作成を統合管理する。

## 2. TTS実装方針 (Gemini-2.5-Flash-TTS)

### 使用API

- `google.genai` SDK の Speech Generation (TTS) 機能を利用。
- モデル: `gemini-2.5-flash-tts`

- **Nagisa**: **Sulafat** (Speech Generation)
- **Shinji**: **Orus** (Speech Generation)
- **Narrator**: **Charon** (Speech Generation)

### 生成フロー

1. `Scripts` シートから `approved=TRUE` かつ `audio_file_path` が空の行を抽出。
2. セリフ (`line_text`) と感情トーン (`tone`) を Gemini に渡し、音声ストリームを取得。
3. `wav` ファイルとして `assets/audio/epXXX/` に保存。
4. `Assets` シートおよび `Scripts` シートにパスを記録。

## 3. 画像生成実装方針

- **初期フェーズ**: `Scripts` シートの `image_prompt` を元に、Stability AI API または OpenAI DALL-E 3 を呼び出す。
- 生成した画像を `assets/images/epXXX/` に保存。

## 4. プログラム構造 (`asset_generator.py`)

- `AssetGenerator` クラス:
  - `generate_voice(text, speaker, tone)`: 個別の音声を生成。
  - `generate_image(prompt)`: 個別の画像を生成。
  - `process_episode(episode_number)`: 指定話数の全未生成アセットを一括処理。

# Soul Reboot - 画像生成仕様書 (Visual Generation Spec)

## 1. 目的

100日間の長期連載において「ナギサ」と「シンジ」のビジュアル的な一貫性を保ち、現実のカレンダーと連動した背景・演出を安定して生成するための技術仕様を定義する。

## 2. 技術スタック

- **画像生成モデル**: Gemini 2.5 Flash Image (`gemini-2.5-flash-image`)
- **SDK**: `google-genai` Python SDK (`from google import genai; from google.genai import types`)
- **一貫性保持**: マスター参照画像（PNG）をマルチモーダル入力として毎回送信し、キャラクターの外見を固定する
- **出力形式**: PNG、16:9（APIパラメータ `image_config=types.ImageConfig(aspect_ratio="16:9")` で指定）
- **生成解像度**: 1344×768（Gemini 2.5 Flash Imageの16:9ネイティブ出力）→ 動画合成時に1920×1080へリサイズ

## 3. キャラクター固定プロンプト (Master Prompts)

### ナギサ (Nagisa)

- **Base**: `1girl, long black hair, sapphire blue eyes, long hair, beautiful detailed eyes, expressionless, kuudere, upper body`
- **Master Image**: `assets/masters/nagisa_master.png`

### シンジ (Shinji)

- **Base**: `1boy, messy brown hair, black eyes, soft expression, young male`
- **Master Image**: `assets/masters/shinji_master.png`

## 4. 環境・服装の動的変化ルール (Dynamic Assets)

服装は `asset_generator.py` の `_get_attire_context()` で自動判定される。背景はシーンごとの `画像プロンプト` で個別に指定する。

> **注意**: 服装・背景の判定は「実行日」ではなく「**公開日**」の曜日に基づく。
> 06:00 JST 以降に実行 → 翌日06:00公開 → 翌日の曜日で判定。
> 00:00〜05:59 JST に実行 → 当日06:00公開 → 当日の曜日で判定。

> **重要**: 学校内シーン（教室・図書室・廊下・屋上など）では、**曜日に関係なく常に制服**を適用する。
> 画像プロンプト内に学校関連のキーワードが含まれていれば自動検出される。

### 平日（月〜金）

- **服装**: `school uniform, necktie, blazer`
- **背景**: 各シーンの `画像プロンプト` に依存（教室・廊下・図書室など）

### 学校内シーン（曜日不問）

- **服装**: `school uniform, necktie, blazer`（休日でも学校内なら制服を強制）
- 検出キーワード: classroom, library, school, hallway, rooftop, 教室, 図書室, 廊下, 屋上 など

### 土日・祝日（学校外）

月ごとの季節服装を適用する。

| 月 | 服装キーワード |
|----|--------------|
| 4月（春） | `cardigan, light coat, sweater` |
| 5月（初夏） | `blouse, thin shirt, dress` |
| 6〜7月（夏） | `short sleeves, summer dress, t-shirt` |

## 5. 演出フィルタ (Emotional Overlay)

覚醒度の上昇に合わせ、プロンプトにビジュアルエフェクトを追加する。

| 覚醒度 | エフェクト |
|--------|-----------|
| 0〜30 | なし |
| 31〜70 | `slight chromatic aberration, subtle digital noise` |
| 71〜100 | `heavy glitch, system error overlay, data fragment particles` |

## 6. YouTube最適化サイズ設定

| 用途 | 最終解像度 | アスペクト比 |
|------|-----------|-------------|
| 動画フレーム（本編） | 1920×1080 | 16:9 |
| サムネイル | 1280×720 | 16:9 |
| 縦長ショート動画 | 1080×1920 | 9:16（オプション） |

画像生成時は Gemini API の `aspect_ratio="16:9"` パラメータで 1344×768 を取得し、`video_compiler.py` で 1920×1080 にリサイズする。

## 7. 生成フロー

1. `Writer AI`（`autonomous_engine.py`）がシーンごとに `画像プロンプト` を生成し、Scriptsシートに記録
2. `asset_generator.py` が本仕様書 §4 の服装ルールを適用し、マスター参照画像 + 自然言語プロンプトをマージ
3. Gemini API にマルチモーダルリクエスト送信（参照画像 → テキスト指示の順）
4. 生成画像を `assets/images/ep{NNN}/ep{NNN}_sc{NN}.png` に保存
5. `Assets` シートに登録（`register_asset()`）

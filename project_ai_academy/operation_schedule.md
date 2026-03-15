# Soul Reboot - 運用スケジュール (Operation Schedule)

## 1. 日次パイプライン（2段階構成）

台本の品質を人間が確認するため、パイプラインを **Phase A（自動）** と **Phase B（承認後自動）** に分離する。

### Phase A: 台本生成（全自動・深夜実行）

| 時間 (JST) | アクション | モジュール |
| :--- | :--- | :--- |
| **00:00** | コメント締切・収集 | `autonomous_engine.py` |
| **00:30** | ニュース・リサーチ（Gemini Flash） | `autonomous_engine.py` |
| **01:00** | プロット生成（Architect / **Opus 4.6**） | `autonomous_engine.py` |
| **01:30** | 台本生成（Writer / Gemini Pro） | `autonomous_engine.py` |
| **01:45** | 台本監修・編集（Editor / **Opus 4.6**） | `autonomous_engine.py` |
| **02:00** | **完了メール送信 → 停止** | `notifier.py` |

Phase A 完了後、メールで「台本確認依頼」を送信し、**人間の承認を待つ**。

### Phase B: アセット〜公開（承認後に一括自動実行）

スプレッドシートの台本を確認し、`approved=TRUE` にした後、以下を一括実行する。

| 順序 | アクション | モジュール |
| :--- | :--- | :--- |
| 1 | 音声生成（TTS） + 画像生成 | `asset_generator.py` |
| 2 | 動画編集・MP4書き出し | `video_compiler.py` |
| 3.5 | サムネイル生成（Scene 1ベース + テキストオーバーレイ） | `asset_generator.py` |
| 4 | YouTube予約アップロード（公開時刻: 翌朝 06:00 JST） | `youtube_uploader.py` |
| 4.5 | サムネイル設定 | `youtube_uploader.py` |
| 5 | **完了メール送信** | `notifier.py` |

各ステップでエラーが発生した場合、その時点で**エラーメール**を送信し停止する。

### 実行コマンド

```bash
# Phase A: 台本生成（タスクスケジューラで毎日 00:00 に実行）
py autonomous_engine.py

# Phase B: 承認後の一括実行（手動トリガー or 承認検知で自動実行）
py publish_pipeline.py --episode N
```

## 2. メール通知

`notifier.py` で以下のタイミングに通知する。環境変数 `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` の設定が必要。

| タイミング | 件名 | 内容 |
| :--- | :--- | :--- |
| Phase A 完了 | `[確認依頼] 第N話 台本生成完了` | タイトル・クリフハンガー・確認チェックリスト |
| Phase B 完了 | `[公開予約] 第N話 YouTube公開予約完了` | YouTube URL・公開予定時刻 |
| エラー発生 | `[エラー] 第N話 エラー発生` | 発生ステップ・エラー内容 |

## 3. YouTube公開設定

- **公開時刻**: 毎朝 06:00 JST（通勤・通学層へリーチ）
- **公開方法**: YouTube Data API v3 の `privacyStatus: "private"` + `publishAt` で予約公開
- **必要な認証**: OAuth 2.0 クライアント（YouTube Data API v3 有効化済み）

## 4. 特例運用 (Special Events)

- **GW・盆・年末年始**: 特別プロットを割り込ませ、季節感を最大化する
  - **GW期間 (5/2-5/6)**: 癒やし回。学校外・私服。パラメータ変動なし
  - **5/7（GW明け）**: 第2フェーズの「バグトリガー」。覚醒度の自律更新が開始
- **パラメータ臨界点**: 信頼度・覚醒度が急変した場合、24時間以内に「号外」ショート動画を作成
- **コメント爆発時**: 採用コメント主への返信をコミュニティ投稿で行う

## 5. 週次メンテナンス

- **毎週日曜 21:00**:
  - 1週間のパラメータ推移の分析
  - Memory_L2 → Memory_L3 への要約（記憶の固定化）
  - モデル（Gemini / Opus 4.6）のプロンプト微調整

## 6. 自動化（GitHub Actions）

Phase A / Phase B ともに GitHub Actions で実行する。

| ワークフロー | トリガー | 概要 |
| :--- | :--- | :--- |
| `phase_a.yml` | 毎日 UTC 15:00（JST 00:00） + 手動 | 台本生成（autonomous_engine.py） |
| `phase_b.yml` | 手動（エピソード番号指定） | アセット生成〜YouTube公開（publish_pipeline.py） |

認証は `CLAUDE_CODE_OAUTH_TOKEN` 環境変数でサブスク Opus 4.6 を利用。
Google Sheets / YouTube の OAuth2 トークンは GitHub Secrets に base64 エンコードで格納。

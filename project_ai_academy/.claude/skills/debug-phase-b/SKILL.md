---
name: debug-phase-b
description: Soul Reboot の Phase B (アセット生成〜公開パイプライン) が失敗した時の定型デバッグ手順。ログ取得、失敗モジュール特定、再実行まで一気通貫で進める。Phase B ワークフローが赤くなった、動画が生成されない、YouTube アップロードが失敗した、などのケースで呼ぶ。
---

# Phase B デバッグ定型手順

Phase B が失敗した時は、いきなり `asset_generator.py` や `publish_pipeline.py` を開かない。
このskillに従って最小の情報から原因を絞り込む。

## Step 1: 直近実行の状況確認

```bash
gh run list --repo insight00studio-web/soul-reboot --workflow=phase_b.yml --limit 3
```

失敗した run ID をユーザーに伝え、どの run を調査するか確認する。

## Step 2: ログから失敗箇所の特定

```bash
gh run view <run-id> --repo insight00studio-web/soul-reboot --log-failed
```

ログ出力は大きいので、**grep で失敗箇所だけ抜き出す**:

```bash
gh run view <run-id> --repo insight00studio-web/soul-reboot --log-failed | grep -E "(ERROR|Error|Traceback|FAIL)" | head -30
```

## Step 3: 失敗パターン分類

以下のよくあるパターンに当てはめる:

| パターン | 症状 | 対処 |
| --- | --- | --- |
| **429 / Rate limit** | `Rate limited. Waiting ...` の繰り返し後に失敗 | `_retry_on_429` の待機時間見直し、もしくは時間を置いて再実行 |
| **TTS 破損WAV** | `generate_voice` で空文字 return | Gemini TTS の一時的不調。時間を置いて再実行 |
| **画像生成失敗** | `generate_image` で空文字、assetパス空 | モデルのコンテンツポリシー抵触の可能性。プロンプト確認 |
| **moviepy エラー** | `AttributeError: module 'moviepy'` など | moviepy==1.0.3 固定の確認。`moviepy.editor` 使用必須 |
| **YouTube アップロード失敗** | `publish_pipeline.py` の最終段 | OAuth トークン期限切れ可能性。`update_token.ps1` 確認 |
| **スプレッドシート書き込み失敗** | `sheets_db.py` で 403/404 | サービスアカウント権限・シートID |

## Step 4: 該当モジュールだけ Read

パターン特定後、**そのモジュール（関数単位）だけ** Read で開く。全体を読まない。

```
Grep で関数名検索 → Read file_path with offset/limit
```

Phase 2 完了後は `asset/` `autonomous/` `sheets/` のサブディレクトリだけ読めば済む。

## Step 5: 修正 → Phase B 再実行

修正が必要ならコミット → push → `skill:regen-phase-b` で再実行。
ログだけで原因不明なら、ユーザーに「run ID XXX でこのエラー、追加情報が必要」と報告して指示を待つ。

## やってはいけないこと

- ログ全文を Claude に読ませる（数万トークン）
- `asset_generator.py` や `publish_pipeline.py` を丸ごと読む
- 推測で広範な修正を入れる（原因未特定のまま）

---
name: regen-phase-b
description: Soul Reboot の既存話の Phase B だけを再生成する定型手順。ユーザーが「第N話のPhase Bを再生成して」「アセット作り直して」等と指示した時に使う。失敗デバッグではなく、意図的な作り直し用（プロンプト変更後の再生成、品質改善の再トライ等）。
---

# Phase B 再生成定型手順

## 使うタイミング

- プロンプト（writer_prompt/editor_prompt 等）を改善したので既存話で再出力したい
- TTS のトーンマッピングを調整したので声を作り直したい
- 画像生成モデルや背景参照を変えたので再生成したい
- 単純にアセットを上書きしたい（スプレッドシートの台本はそのまま）

**前提**: 該当話の Phase A（台本・メモリ・パラメータ）は既にスプレッドシートに存在すること。

## Step 1: 再生成対象の確認

ユーザーが話数を指定しているか確認。していなければ聞く。

## Step 2: 直近の Phase B run 確認（重複防止）

```bash
gh run list --repo insight00studio-web/soul-reboot --workflow=phase_b.yml --limit 5
```

同じ話が in_progress なら待つ。

## Step 3: 実行

```bash
gh workflow run phase_b.yml --repo insight00studio-web/soul-reboot -f episode=<N>
```

## Step 4: ユーザーに run URL を返す

```
https://github.com/insight00studio-web/soul-reboot/actions/runs/<run-id>
```

完了まで約50分。ユーザーに「完了まで約50分かかります」と伝える。

## Step 5: 完了後

`skill:check-phase-status` で成功確認 → 失敗なら `skill:debug-phase-b` へ。

## 注意

- GitHub Actions 無料枠を消費する（1回 ≈ 80分）
- 既存の YouTube 動画があれば **上書きではなく重複アップロード** になる可能性。
  実運用時は `publish_pipeline.py` の挙動を確認。

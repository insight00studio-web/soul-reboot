---
name: trigger-episode
description: Soul Reboot の Phase A (台本生成) または Phase B (アセット生成〜公開) を手動トリガーする定型手順。ユーザーが「第N話を生成して」「Phase A 回して」等と指示した時に使う。トークン更新・前提チェックも含む。
---

# エピソード手動トリガー手順

## ステップ0: トークン更新（必須・毎回）

Phase A / Phase B を実行する前に**必ず**トークンを更新する。
期限切れでも有効でも、常に実行してよい（数秒で完了、冪等）。

```powershell
& "C:\Users\uca-n\youtube\update_token.ps1"
```

出力に `OK: CLAUDE_CREDENTIALS_JSON updated` が含まれていれば成功。
失敗した場合はトリガーを中断しユーザーに報告する。

## Phase A（台本生成）手動実行

**いつ使う**: Phase A の自動実行（毎日 JST 00:00）が失敗した時、または話数を手動で進めたい時。

```bash
gh workflow run phase_a.yml --repo insight00studio-web/soul-reboot
```

Phase A は完了後、自動で Phase B をトリガーする設計。

## Phase B（特定話のアセット生成〜公開）手動実行

**いつ使う**: 既存話の Phase A はあるが Phase B だけ失敗 or 未実行の時。

```bash
gh workflow run phase_b.yml --repo insight00studio-web/soul-reboot -f episode=<N>
```

## 実行前チェック（ステップ0の後）

1. **直近 run の重複防止**: 同じ話が既に生成中でないか確認
   ```bash
   gh run list --repo insight00studio-web/soul-reboot --limit 5
   ```
2. **GitHub Actions 無料枠**: 月2,000分。1話あたり約80分消費。月25話超で超過警告。

## 実行後

トリガー後はユーザーに run URL を返す:
```
https://github.com/insight00studio-web/soul-reboot/actions/runs/<run-id>
```

完了確認は `skill:check-phase-status` で。失敗したら `skill:debug-phase-b` へ。

---
name: trigger-episode
description: Soul Reboot の Phase A (台本生成) または Phase B (アセット生成〜公開) を手動トリガーする定型手順。ユーザーが「第N話を生成して」「Phase A 回して」等と指示した時に使う。前提チェック（トークン有効期限、直近run状態）も含む。
---

# エピソード手動トリガー手順

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

## 実行前チェック

1. **CLAUDE_CODE_OAUTH_TOKEN 期限**: 約36〜48時間で切れる。前回 `update_token.ps1` を実行した時刻を確認。
2. **直近 run の重複防止**: 同じ話が既に生成中でないか確認
   ```bash
   gh run list --repo insight00studio-web/soul-reboot --limit 5
   ```
3. **GitHub Actions 無料枠**: 月2,000分。1話あたり約80分消費。月25話超で超過警告。

## 実行後

トリガー後はユーザーに run URL を返す:
```
https://github.com/insight00studio-web/soul-reboot/actions/runs/<run-id>
```

完了確認は `skill:check-phase-status` で。失敗したら `skill:debug-phase-b` へ。

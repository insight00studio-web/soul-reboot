---
name: check-phase-status
description: Soul Reboot の Phase A/B ワークフロー実行状況を確認する定型手順。ユーザーが「Phase B終わった？」「今どうなってる？」「run の状態見せて」等と聞いた時に使う。直近runの成否確認と、必要なら失敗ログ抜粋まで行う。
---

# Phase A/B 実行状況確認

## Step 1: 直近 run のステータス

```bash
gh run list --repo insight00studio-web/soul-reboot --limit 5
```

出力から以下を判断:
- `in_progress`: 実行中。経過時間を報告。
- `completed success`: 成功。所要時間とURLを報告。
- `completed failure`: 失敗。次のステップへ。

## Step 2: 失敗している場合

失敗した run のIDを特定して、失敗要因だけ抜粋:

```bash
gh run view <run-id> --repo insight00studio-web/soul-reboot --log-failed | grep -E "(ERROR|Error|Traceback|FAIL)" | head -20
```

ログ全文を Claude のコンテキストに入れない。**grep で要約**すること。

## Step 3: ユーザーへの報告フォーマット

```
直近 run:
- #24608414832 phase_b (ep12): in_progress (35秒経過)
- #24601667550 phase_b (ep11): completed success (54m56s)

URL: https://github.com/insight00studio-web/soul-reboot/actions/runs/24608414832
```

失敗なら簡潔なエラー要約を添える。深掘りが必要そうなら `skill:debug-phase-b` を提案する。

## 補足: 特定の話数で絞りたい時

workflow_dispatch のinputは `gh run list` には出ないので、run view で確認:

```bash
gh run view <run-id> --repo insight00studio-web/soul-reboot --json displayTitle,status,conclusion,createdAt
```

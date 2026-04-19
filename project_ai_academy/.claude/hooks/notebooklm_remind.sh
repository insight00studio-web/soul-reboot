#!/bin/bash
# Stop hook: ターン終了時にマーカーファイルをチェックし、プロンプト編集があればリマインダーを出す

set +e

repo_root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
pending_file="$repo_root/.claude/tmp/notebooklm_pending"

if [ -f "$pending_file" ] && [ -s "$pending_file" ]; then
  files=$(sort -u "$pending_file")

  cat <<EOF

========================================================
📘 NotebookLM 同期リマインダー
========================================================
以下のプロンプトファイルが編集されました:

$files

Drive 連携済みの Google Doc を更新してください (Step 7-C):
  1. 上記ローカル .md の内容をコピー
  2. Drive の同名 Google Doc を開く
  3. 全選択 → 削除 → ペースト
  4. NotebookLM でそのソースの ⋮ メニュー → 「再同期」

（このリマインダーは今ターンで消化済み。次回の編集時に再度表示されます）
========================================================
EOF

  rm -f "$pending_file"
fi

exit 0

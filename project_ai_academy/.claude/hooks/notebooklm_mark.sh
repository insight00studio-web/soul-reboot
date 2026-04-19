#!/bin/bash
# PostToolUse hook: prompts/*.md への Edit/Write を検知してマーカーファイルに記録する
# Stop hook (notebooklm_remind.sh) と連動して、ターン終了時にリマインダーを出す

set +e

input=$(cat)

# tool_input.file_path を JSON から抽出（jq 等に依存しない）
file_path=$(printf '%s' "$input" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)".*/\1/')

# prompts/<name>.md にマッチするもののみマークする（フォワード/バックスラッシュ両対応）
if printf '%s' "$file_path" | grep -qE '[/\\]prompts[/\\][^/\\]+\.md$'; then
  repo_root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
  tmp_dir="$repo_root/.claude/tmp"
  mkdir -p "$tmp_dir" 2>/dev/null
  printf '%s\n' "$file_path" >> "$tmp_dir/notebooklm_pending"
fi

exit 0

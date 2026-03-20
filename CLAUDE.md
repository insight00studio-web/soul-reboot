# プロジェクト設定

## 言語設定

承認・確認の際の表示は常に日本語で行うこと。

---

## プロジェクト概要

**Soul Reboot - 100日後の君へ -**
AIと人間の100日間を描く自律型YouTubeチャンネル。毎日1話を自動生成・公開する。

- **GitHubリポジトリ**: `insight00studio-web/soul-reboot`
- **主要ディレクトリ**: `project_ai_academy/`
- **詳細仕様**: `project_ai_academy/project_design.md` / `project_ai_academy/operation_schedule.md`

### パイプライン構成

| フェーズ | 内容 | トリガー |
| --- | --- | --- |
| Phase A | 台本生成（autonomous_engine.py） | 毎日 JST 00:00 自動 / 手動 |
| Phase B | アセット生成〜YouTube公開（publish_pipeline.py） | Phase A 完了後に自動トリガー / 手動 |

---

## 重要な制約・ルール

- **approved フラグ**: `autonomous_engine.py` は `approved=TRUE` で台本を書き込む（手動承認不要）
- **moviepy バージョン**: `moviepy==1.0.3` 固定（v2 は `moviepy.editor` が削除されており使用不可）
- **TTS 音声設定**: NAGISA=`Despina`, SHINJI=`Orus`, NARRATOR=`Charon`, SYSTEM=`Kore`
- **台本品質基準**: 4シーン以上・20行以上・動画尺約5分

---

## よく使うコマンド

```bash
# Phase B 手動実行（エピソード番号を指定）
gh workflow run phase_b.yml --repo insight00studio-web/soul-reboot -f episode=N

# Phase A 手動実行
gh workflow run phase_a.yml --repo insight00studio-web/soul-reboot

# ワークフロー実行状況確認
gh run list --repo insight00studio-web/soul-reboot --limit 5
```

```powershell
# CLAUDE_CODE_OAUTH_TOKEN を GitHub Secret に更新（毎晩23時までに実行）
./update_token.ps1
```

---

## 注意事項

- **GitHub Actions 無料枠**: 非公開リポジトリは月2,000分。1話あたり約80分消費するため、月25話超で超過する。超過時は GitHub Pro ($4/月) へアップグレードすること。
- **CLAUDE_CODE_OAUTH_TOKEN**: 約36〜48時間で期限切れ。`update_token.ps1` で毎日更新が必要。
- **GitHub Actions ランナーはエフェメラル**: 音声ファイルなどは毎回再生成される（スプレッドシートにパスが残っていてもファイルが存在しない場合は再生成する実装済み）。

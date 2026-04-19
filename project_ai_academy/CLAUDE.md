# project_ai_academy — Claude Code 作業指針

ルートの `../CLAUDE.md` に加え、このディレクトリ内での作業時は以下のルールを必ず守ること。
目的はトークン消費の削減と、物語品質を担保する領域への集中。

---

## 大ファイルは丸読み禁止

以下のファイルは行数が大きく、全読みすると1回で 20K〜30K トークンを消費する。
**必ず Grep で目的のシンボル・キーワードを先に特定してから、Read を offset/limit で部分読み**すること。

| ファイル | 行数 | 部分読みの典型 |
| --- | --- | --- |
| `autonomous_engine.py` | ~1054 | 段階ごとに関数が並ぶ。Architect/Writer/Editorの該当関数だけ読む |
| `asset_generator.py` | ~900 | TTS→画像→マスター→動画コンパイルの順。該当ブロックだけ読む |
| `sheets_db.py` | ~700 | 読み/書き/スキーマで分離。該当メソッドだけ読む |

例外: 全体構造を把握する必要がある初回のみ、Explore エージェント経由で要約させる。本スレッドに丸読みしない。

モジュール分割（Phase 2）完了後は、対応するサブディレクトリだけ読めば済むので、このルールは該当しなくなる。

---

## Phase B デバッグは skill 経由で

Phase B（アセット生成〜公開）が失敗した時は、いきなり `asset_generator.py` を読まずに、
まず `skill:debug-phase-b` を呼ぶ。ログ取得 → 該当モジュール特定 → 再実行の定型手順が入っている。

同様に:
- 新話 Phase A/B トリガー: `skill:trigger-episode`
- 既存話の Phase B 再生成: `skill:regen-phase-b`
- 実行状況確認: `skill:check-phase-status`

これらは on-demand ロードなので、使わない時はコンテキストを食わない。

---

## 物語品質に関わる領域（攻め：投資対象）

以下のファイル／ディレクトリは台本品質・キャラ一貫性・100日弧の設計に直結する。
**ここだけは惜しまず読み、慎重に編集する**こと。

- `prompts/architect_prompt.md` / `writer_prompt.md` / `editor_prompt.md`
- `narrative/`（Phase 3 以降に新設予定）
  - `arc_plan.md`: 100日弧の大筋
  - `character_bible.md`: キャラ不変要素
  - `episode_memory/ep_{NN}.yaml`: 話ごとの構造化メモリ

これらに触れる時は、該当箇所を全読みしてから提案する。トークンを節約しすぎて質を落とさないこと。

---

## 仕様確認は外部サービスにオフロード

以下の仕様ドキュメントは NotebookLM に投入済み想定。**Claude Code では全読みしない**。

- `project_design.md` / `operation_schedule.md`
- `youtube_channel_strategy.md` / `spreadsheet_db_design.md`

ユーザーが明示的に「この仕様について」と聞いてきた場合のみ、必要箇所だけ Grep で引く。

---

## 運用コマンドの定型

よく使う gh/git コマンドは `.claude/settings.json` で allowlist 済み。承認プロンプトは出ない想定。
skill を経由せずに直接叩いて良いもの:

```bash
gh workflow run phase_b.yml --repo insight00studio-web/soul-reboot -f episode=N
gh workflow run phase_a.yml --repo insight00studio-web/soul-reboot
gh run list --repo insight00studio-web/soul-reboot --limit 5
gh run view <run-id> --repo insight00studio-web/soul-reboot --log
```

---

## 絶対ルール

- `moviepy==1.0.3` 固定（v2 非対応、`moviepy.editor` が削除されている）
- TTS 声優割り当て: NAGISA=`Despina`, SHINJI=`Orus`, NARRATOR=`Charon`, SYSTEM=`Kore`
- `autonomous_engine.py` は `approved=TRUE` で台本書き込み（手動承認なし）
- 台本品質基準: 4シーン以上・20行以上・動画尺約5分

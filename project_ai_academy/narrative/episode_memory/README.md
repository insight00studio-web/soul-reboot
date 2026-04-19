# episode_memory/ — 話ごとの構造化記憶

> Phase A 完了時に `ep_{NN}.yaml` が自動生成される。次話生成時に前話の状態を Architect に注入するために使う。

## ファイル命名規則

- `ep_01.yaml`, `ep_02.yaml`, ... `ep_29.yaml`
- エピソード番号は **ゼロ埋め2桁**。29話完結のため3桁は不要。

## 生成タイミング

`autonomous/pipeline.py` の `step_finalize` 前後で `autonomous/memory.py::write_episode_memory(episode_number, plot, script_lines)` が自動書き出し。

## 既存エピソード（ep_01〜ep_11 相当）の扱い

Phase 3 導入時点（本日時点で Day 12）では過去話分の YAML は存在しない。
`memory.py` はファイルが無い場合、既存の `memory_l2.json` と Sheets の L1 文脈にフォールバックする。
つまり **空配列でも動作する** 前提で設計されている。過去話分の手動バックフィルは不要（必要になったら後日）。

## スキーマ

`_template.yaml` を参照。必須フィールド:

- `episode` (int): 話数
- `date` (YYYY-MM-DD): 物語内日付
- `arc_phase`: `PHASE_1_happy_misrecognition` | `PHASE_2_soul_noise` | `PHASE_3_sanctuary_collapse` | `PHASE_4_ending`
- `title`: 確定タイトル
- `key_events`: 主要な出来事（配列）
- `character_state`: 話末のキャラ状態
  - `NAGISA`: `{ emotion, awareness_of_ai, relation_to_SHINJI }`
  - `SHINJI`: `{ emotion, hidden_motive, relation_to_NAGISA }`
- `foreshadowing`:
  - `opened`: このエピソードで追加した伏線 ID の配列
  - `resolved`: このエピソードで回収した伏線 ID の配列
- `parameters`: `{ trust, awakening, record }` の話末値
- `cliffhanger`: 次話への引き文
- `next_ep_hook`: 次話が踏まえるべき感情的・状況的な繋ぎ（Architect が読む）

## 読み込み順

次話（第 N 話）生成時:

1. `ep_{N-1:02d}.yaml` を読む → `<previous_episode_state>` に展開
2. `ep_{N-2:02d}.yaml` と `ep_{N-3:02d}.yaml` があれば要約して `<recent_trajectory>` に追加（任意）
3. 見つからなければ既存の L2 JSON / Sheets L1 にフォールバック

## 手動編集

基本は自動生成だが、手動で品質を上げたい場合は直接編集してよい。
編集後は次話生成で即座に反映される。

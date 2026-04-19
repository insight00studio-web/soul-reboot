"""autonomous パッケージ - Phase A（自律生成）の実装層。

このパッケージは段階別に分かれている:
  - utils:     共通ヘルパ（load_prompt, 物語内日付、scene_plan サマリ 等）
  - collect:   step_collect_news / step_collect_analytics / step_score_comments
  - architect: _build_architect_prompt, step_architect
  - writer:    step_writer
  - editor:    step_editor
  - metadata:  _calculate_viewer_delta, step_update_metadata, step_finalize
  - pipeline:  main（各 step を順番に呼ぶオーケストレータ）

既存の `python autonomous_engine.py` 実行は引き続き動作する。
autonomous_engine.py はこのパッケージの facade である。
"""

from .pipeline import main

__all__ = ["main"]

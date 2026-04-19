"""autonomous_engine.py - autonomous パッケージの facade。

実装は autonomous/ 以下に分割されている:
  - autonomous/utils.py     : 共通ヘルパ（load_prompt, 物語内日付 等）
  - autonomous/collect.py   : ニュース・Analytics・コメントスコアリング
  - autonomous/architect.py : Architect 段階（Opus でプロット生成）
  - autonomous/writer.py    : Writer 段階（Gemini で台本生成）
  - autonomous/editor.py    : Editor 段階（Opus で監修・品質スコア）
  - autonomous/metadata.py  : 伏線・パラメータ・L2記憶更新・完了レポート
  - autonomous/pipeline.py  : main（各 step を順に呼ぶオーケストレータ）

既存の `python autonomous_engine.py` 実行は引き続き動作する。
"""

from autonomous.pipeline import main

__all__ = ["main"]


if __name__ == "__main__":
    main()

"""asset_generator.py - asset パッケージの facade。

実装は asset/ 以下に分割されている:
  - asset/constants.py   : レート制限・トーン/場所/服装マップ
  - asset/attire.py      : AttireMixin（服装・日付・場所推定）
  - asset/master.py      : MasterMixin（マスター参照画像の読込・生成）
  - asset/tts.py         : TTSMixin（音声生成）
  - asset/image.py       : ImageMixin（画像・サムネイル生成）
  - asset/orchestrator.py: AssetGenerator 本体

既存コードの `from asset_generator import AssetGenerator` と `python asset_generator.py`
実行（main）は引き続き動作する。
"""

from asset.orchestrator import AssetGenerator, main

__all__ = ["AssetGenerator", "main"]


if __name__ == "__main__":
    main()

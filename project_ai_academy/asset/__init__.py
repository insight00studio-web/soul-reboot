"""asset パッケージ - アセット生成（TTS・画像・サムネイル）の実装層。

このパッケージは機能別に分かれている:
  - constants: レート制限・トーン/服装/場所マップなどの定数
  - attire:    AttireMixin（服装・日付・場所推定）
  - master:    MasterMixin（マスター参照画像の読込・生成）
  - tts:       TTSMixin（音声生成）
  - image:     ImageMixin（画像・サムネイル生成）
  - orchestrator: AssetGenerator 本体（全 Mixin を合成）

既存コードは `from asset_generator import AssetGenerator` を使い続けて良い。
asset_generator.py はこのパッケージの facade である。
"""

from .orchestrator import AssetGenerator

__all__ = ["AssetGenerator"]

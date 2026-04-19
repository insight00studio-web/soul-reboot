"""asset/master.py - マスター参照画像（基本・私服）の読み込み・生成。

MasterMixin は AssetGenerator に合成される。単独では使わない。
前提: self.client, self.image_model, self.base_dir, self.char_image_base,
     self.master_image_paths, self.outfit_master_paths,
     self._master_image_cache, self._outfit_master_cache,
     self._retry_on_429 が利用可能であること。
"""

import time

from google.genai import types

from .constants import (
    IMAGE_RETRY_WAIT_429,
    MAX_RETRIES,
    OUTFIT_DEFINITIONS,
    RATE_LIMIT_WAIT,
)


class MasterMixin:
    """マスター参照画像の読み込みと自動生成を担当する Mixin。"""

    def _load_master_image_bytes(self, char_key: str):
        """マスター参照画像をディスクから読み込みキャッシュする。存在しない場合はNoneを返す"""
        if char_key in self._master_image_cache:
            return self._master_image_cache[char_key]

        img_path = self.master_image_paths.get(char_key)
        if img_path is None or not img_path.exists():
            print(f"  [IMAGE] WARN: Master image not found for {char_key}: {img_path}")
            return None

        with open(img_path, "rb") as f:
            data = f.read()

        self._master_image_cache[char_key] = data
        print(f"  [IMAGE] Loaded master image for {char_key} ({len(data)} bytes)")
        return data

    def _load_outfit_master_bytes(self, char_key: str, outfit_key: str):
        """私服マスター画像をキャッシュ付きで読み込む。存在しない場合は None。"""
        cache_key = f"{char_key}_{outfit_key}"
        if cache_key in self._outfit_master_cache:
            return self._outfit_master_cache[cache_key]
        img_path = self.outfit_master_paths.get(char_key, {}).get(outfit_key)
        if img_path is None or not img_path.exists():
            return None
        with open(img_path, "rb") as f:
            data = f.read()
        self._outfit_master_cache[cache_key] = data
        print(f"  [IMAGE] Loaded outfit master: {char_key}/{outfit_key} ({len(data)} bytes)")
        return data

    def _generate_outfit_master(self, char_key: str, outfit_key: str) -> bool:
        """指定キャラ・服装パターンのマスター参照画像を生成・保存する"""
        outfit_desc, context = OUTFIT_DEFINITIONS[char_key][outfit_key]
        char_base = self.char_image_base.get(char_key, "")
        prompt = (
            f"Draw a full-body anime character reference illustration. "
            f"Character traits: {char_base}. "
            f"The character MUST look EXACTLY like in the reference image (same face, hair, eyes).\n"
            f"Outfit: {outfit_desc}\n"
            f"Context: {context}\n"
            "Style: clean anime illustration, full body visible, neutral standing pose, "
            "simple white background. This is a character costume reference sheet. "
            "High quality, consistent character design, no background scenery."
        )
        master_bytes = self._load_master_image_bytes(char_key)
        contents = []
        if master_bytes:
            contents.append(types.Part.from_bytes(data=master_bytes, mime_type="image/png"))
        contents.append(prompt)

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.image_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio="1:1"),
                    ),
                )
                image_data = None
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        image_data = part.inline_data.data
                        break
                if not image_data:
                    print(f"    ERROR: No image data for outfit master {char_key}/{outfit_key}")
                    return False
                masters_dir = self.base_dir / "assets" / "masters"
                masters_dir.mkdir(parents=True, exist_ok=True)
                file_path = masters_dir / f"{char_key.lower()}_casual_{outfit_key}.png"
                with open(file_path, "wb") as f:
                    f.write(image_data)
                print(f"    [OUTFIT MASTER] Saved: {file_path}")
                time.sleep(RATE_LIMIT_WAIT)
                return True
            except Exception as e:
                if self._retry_on_429(e, IMAGE_RETRY_WAIT_429, attempt, "Outfit master generation"):
                    continue
                return False
        return False

    def _ensure_outfit_masters(self):
        """私服マスター画像が不足している場合に自動生成する"""
        missing = [
            (char_key, outfit_key)
            for char_key in OUTFIT_DEFINITIONS
            for outfit_key in OUTFIT_DEFINITIONS[char_key]
            if not self.outfit_master_paths[char_key][outfit_key].exists()
        ]
        if not missing:
            return
        print(f"[OUTFIT MASTERS] {len(missing)}個の私服マスター画像を生成します...")
        for char_key, outfit_key in missing:
            print(f"  Generating: {char_key} / {outfit_key}...")
            self._generate_outfit_master(char_key, outfit_key)

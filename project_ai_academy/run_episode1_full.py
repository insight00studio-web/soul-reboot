"""
run_episode1_full.py
Soul Reboot - 第1話 完全リセット → 台本生成 → 全承認 → TTS/画像生成 通し実行スクリプト

処理フロー:
    1. スプレッドシートの第1話データを全削除
    2. ローカルの音声・画像ファイル (assets/audio/ep001/, assets/images/ep001/) を削除
    3. 再生成パイプライン（ニュース→プロット→台本→メタデータ）
    4. 台本を全承認（承認済=TRUE）
    5. TTS音声・シーン画像を全生成
    6. CURRENT_EPISODE を 2 に設定

実行コマンド:
    python run_episode1_full.py
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from sheets_db import SoulRebootDB
from autonomous_engine import (
    step_collect_news,
    step_score_comments,
    step_architect,
    step_writer,
    step_update_metadata,
)
from asset_generator import AssetGenerator

load_dotenv()

EPISODE_NUMBER = 1
BASE_DIR = Path(__file__).parent


def reset_spreadsheet(db: SoulRebootDB) -> None:
    print("\n[RESET] スプレッドシートの第1話データを削除中...")
    n_scripts = db.delete_episode_scripts(EPISODE_NUMBER)
    n_fs      = db.delete_episode_foreshadowing(EPISODE_NUMBER)
    n_params  = db.delete_episode_parameters(EPISODE_NUMBER)
    n_mem     = db.delete_episode_memory_l2(EPISODE_NUMBER)
    print(f"  削除完了: Scripts={n_scripts}行 / Foreshadowing={n_fs}行 / "
          f"Parameters={n_params}行 / Memory_L2={n_mem}行")


def reset_local_files() -> None:
    for subdir in ["audio/ep001", "images/ep001"]:
        target = BASE_DIR / "assets" / Path(subdir)
        if target.exists():
            deleted = list(target.glob("*.*"))
            for f in deleted:
                f.unlink()
            print(f"[RESET] ファイル削除: {len(deleted)}件 ({target})")
        else:
            print(f"[RESET] ディレクトリなし（スキップ）: {target}")


def main():
    print("=" * 60)
    print("Soul Reboot - 第1話 完全通し実行")
    print(f"   実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: 環境変数 GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("ERROR: 環境変数 SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        sys.exit(1)

    # --- STEP 1: リセット ---
    db = SoulRebootDB(spreadsheet_id)
    config = db.get_config()
    reset_spreadsheet(db)
    reset_local_files()

    # --- STEP 2: 台本生成 ---
    print("\n[GENERATE] 第1話を生成します...")
    news         = step_collect_news(db, config)
    top_comments = step_score_comments(db)
    plot         = step_architect(db, config, EPISODE_NUMBER, news, top_comments)
    step_writer(db, config, EPISODE_NUMBER, plot)
    step_update_metadata(db, EPISODE_NUMBER, plot)

    # --- STEP 3: 全承認 ---
    print("\n[APPROVE] 台本を全承認します...")
    approved_count = db.approve_all_scripts(EPISODE_NUMBER)
    print(f"  承認完了: {approved_count}行")

    # --- STEP 4: TTS/画像生成 ---
    print("\n[ASSET] TTS・画像生成を開始します...")
    generator = AssetGenerator(spreadsheet_id)
    generator.process_episode(EPISODE_NUMBER)

    # --- STEP 5: CURRENT_EPISODE を 2 に設定 ---
    db.set_config("CURRENT_EPISODE", 2)

    # --- 完了レポート ---
    print("\n" + "=" * 60)
    print("DONE: 第1話 完全通し実行完了！")
    print(f"   タイトル:「{plot.get('title', '（未設定）')}」")
    print(f"   承認行数: {approved_count}行")
    print(f"   音声: assets/audio/ep001/")
    print(f"   画像: assets/images/ep001/")
    print("=" * 60)


if __name__ == "__main__":
    main()

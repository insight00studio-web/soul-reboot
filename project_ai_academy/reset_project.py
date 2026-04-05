"""
reset_project.py
Soul Reboot - プロジェクト全リセットスクリプト

実行すると以下を行う：
  1. スプレッドシートの全エピソードデータを削除（ヘッダー行は保持）
  2. Config の CURRENT_EPISODE を 1 にリセット
  3. memory_l1.json / memory_l2.json を空にリセット
  4. episode_number.txt を削除

実行方法:
  cd project_ai_academy
  python reset_project.py
"""

import os
import sys
import json
import time

# Windows環境でのUTF-8出力対応
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# sheets_db は同ディレクトリにある
from sheets_db import (
    SoulRebootDB,
    SHEET_EPISODES, SHEET_SCRIPTS, SHEET_FORESHADOWING, SHEET_COMMENTS,
    SHEET_PARAMETERS, SHEET_ASSETS, SHEET_NEWS, SHEET_MEMORY_L2, SHEET_ANALYTICS,
)

# ===================================================================
# 設定
# ===================================================================

SPREADSHEET_ID = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")

# リセット対象シート（Config と masters は除外）
SHEETS_TO_CLEAR = [
    SHEET_EPISODES,
    SHEET_SCRIPTS,
    SHEET_FORESHADOWING,
    SHEET_COMMENTS,
    SHEET_PARAMETERS,
    SHEET_ASSETS,
    SHEET_NEWS,
    SHEET_MEMORY_L2,
    SHEET_ANALYTICS,
]

BASE_DIR = os.path.dirname(__file__)
MEMORY_L1_PATH = os.path.join(BASE_DIR, "memory_l1.json")
MEMORY_L2_PATH = os.path.join(BASE_DIR, "memory_l2.json")
EPISODE_NUMBER_PATH = os.path.join(BASE_DIR, "episode_number.txt")


# ===================================================================
# スプレッドシートリセット
# ===================================================================

def clear_sheet_keep_header(db: SoulRebootDB, sheet_name: str) -> None:
    """シートのデータ行をすべて削除し、ヘッダー行だけ残す。"""
    ws = db.spreadsheet.worksheet(sheet_name)
    all_values = ws.get_all_values()

    if not all_values:
        print(f"  SKIP: {sheet_name} — 空のシート")
        return

    header = all_values[0]
    data_row_count = len(all_values) - 1

    if data_row_count == 0:
        print(f"  SKIP: {sheet_name} — データ行なし")
        return

    # シート全体をクリアしてヘッダーを復元
    ws.clear()
    time.sleep(0.5)  # Write API レート制限を避ける
    ws.append_row(header, value_input_option="RAW")
    print(f"  DONE: {sheet_name} — {data_row_count}行削除, ヘッダー復元")


def reset_spreadsheet(db: SoulRebootDB) -> None:
    print("\n[1/3] スプレッドシートのリセット開始...")

    for sheet_name in SHEETS_TO_CLEAR:
        try:
            clear_sheet_keep_header(db, sheet_name)
            time.sleep(1.0)  # シート間でウェイト（Write 429対策）
        except Exception as e:
            print(f"  ERROR: {sheet_name} — {e}")

    # CURRENT_EPISODE を 1 にリセット
    db.set_config("CURRENT_EPISODE", 1)
    print("  DONE: Config CURRENT_EPISODE = 1")

    print("[1/3] スプレッドシートのリセット完了")


# ===================================================================
# ローカルファイルリセット
# ===================================================================

def reset_local_files() -> None:
    print("\n[2/3] ローカルメモリファイルのリセット...")

    # memory_l1.json
    with open(MEMORY_L1_PATH, "w", encoding="utf-8") as f:
        json.dump({"recent_episodes": []}, f, ensure_ascii=False, indent=4)
    print("  DONE: memory_l1.json — リセット完了")

    # memory_l2.json
    with open(MEMORY_L2_PATH, "w", encoding="utf-8") as f:
        json.dump({"episodes": []}, f, ensure_ascii=False, indent=4)
    print("  DONE: memory_l2.json — リセット完了")

    # episode_number.txt
    if os.path.exists(EPISODE_NUMBER_PATH):
        os.remove(EPISODE_NUMBER_PATH)
        print("  DONE: episode_number.txt — 削除完了")
    else:
        print("  SKIP: episode_number.txt — 存在しない")

    print("[2/3] ローカルファイルのリセット完了")


# ===================================================================
# メイン
# ===================================================================

def main():
    print("=" * 50)
    print("Soul Reboot プロジェクトリセット")
    print("=" * 50)
    print()
    print("【注意】以下の操作を行います：")
    print("  - スプレッドシートの全エピソードデータを削除")
    print("  - CURRENT_EPISODE を 1 にリセット")
    print("  - memory_l1.json / memory_l2.json を空にリセット")
    print("  - episode_number.txt を削除")
    print()

    confirm = input("続行しますか？ (yes/no): ").strip().lower()
    if confirm != "yes":
        print("キャンセルしました。")
        return

    if not SPREADSHEET_ID:
        print("ERROR: 環境変数 SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        return

    # スプレッドシート接続
    print("\nスプレッドシートに接続中...")
    db = SoulRebootDB(SPREADSHEET_ID)

    # リセット実行
    reset_spreadsheet(db)
    reset_local_files()

    print()
    print("=" * 50)
    print("[3/3] リセット完了！")
    print()
    print("次のステップ：")
    print("  1. YouTubeの動画（第1〜20話）をYouTube Studioから手動削除")
    print("  2. ./update_token.ps1 でトークンを更新")
    print("  3. Phase A を実行して第1話の台本生成を開始")
    print("     gh workflow run phase_a.yml --repo insight00studio-web/soul-reboot")
    print("=" * 50)


if __name__ == "__main__":
    main()

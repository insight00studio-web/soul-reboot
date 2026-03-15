"""
reset_episode1.py
Soul Reboot - 第1話 完全リセット＆再生成スクリプト

処理フロー:
    1. スプレッドシートの第1話データを全削除
    2. ローカルの音声ファイル (assets/audio/ep001/) を削除
    3. 再生成パイプラインを実行（ニュース→プロット→台本→メタデータ）
    4. CURRENT_EPISODE を 2 に設定

実行コマンド:
    python reset_episode1.py
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

load_dotenv()

EPISODE_NUMBER = 1
BASE_DIR = Path(__file__).parent


def reset_spreadsheet(db: SoulRebootDB) -> None:
    """スプレッドシートの第1話データをすべて削除する"""
    print("\n[RESET] スプレッドシートの第1話データを削除中...")

    n_scripts = db.delete_episode_scripts(EPISODE_NUMBER)
    n_fs      = db.delete_episode_foreshadowing(EPISODE_NUMBER)
    n_params  = db.delete_episode_parameters(EPISODE_NUMBER)
    n_mem     = db.delete_episode_memory_l2(EPISODE_NUMBER)

    print(f"  削除完了: Scripts={n_scripts}行 / Foreshadowing={n_fs}行 / "
          f"Parameters={n_params}行 / Memory_L2={n_mem}行")


def reset_local_files() -> None:
    """ローカルの音声ファイルを削除する"""
    audio_dir = BASE_DIR / "assets" / "audio" / "ep001"
    if audio_dir.exists():
        deleted = list(audio_dir.glob("*.wav"))
        for f in deleted:
            f.unlink()
        print(f"\n[RESET] 音声ファイル削除: {len(deleted)}件 ({audio_dir})")
    else:
        print(f"\n[RESET] 音声ディレクトリなし（スキップ）: {audio_dir}")


def main():
    print("=" * 60)
    print("Soul Reboot - 第1話 完全リセット＆再生成")
    print(f"   実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: 環境変数 GEMINI_API_KEY が設定されていません")
        sys.exit(1)

    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("ERROR: 環境変数 SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        sys.exit(1)

    # DB接続
    db = SoulRebootDB(spreadsheet_id)
    config = db.get_config()

    # ① リセット
    reset_spreadsheet(db)
    reset_local_files()

    # ② 再生成パイプライン
    print("\n[REGENERATE] 第1話を再生成します...")

    news         = step_collect_news(db, config)
    top_comments = step_score_comments(db)
    plot         = step_architect(db, config, EPISODE_NUMBER, news, top_comments)
    step_writer(db, config, EPISODE_NUMBER, plot)
    step_update_metadata(db, EPISODE_NUMBER, plot)

    # ③ CURRENT_EPISODE を 2 に設定（step_finalize は呼ばない）
    db.set_config("CURRENT_EPISODE", 2)

    # ④ 完了レポート
    print("\n" + "=" * 60)
    print("DONE: 第1話 リセット＆再生成完了！")
    print(f"   タイトル:「{plot.get('title', '（未設定）')}」")
    print(f"   感情曲線: {plot.get('emotional_curve', '')}")
    print(f"   クリフハンガー: {str(plot.get('cliffhanger', ''))[:50]}...")
    print()
    print("📋 次のアクション（スプレッドシートを確認してください）:")
    print("   1. [📜 Scripts]       台本を確認 → approved=TRUE で承認")
    print("   2. [📋 Episodes]      タイトル・プロット要約を確認・修正")
    print("   3. [🔮 Foreshadowing] 新しい伏線が登録されているか確認")
    print("   4. [📊 Parameters]    パラメータ値を確認")
    print("   5. [📖 Memory_L2]     第1話の要約が入っているか確認")
    print("   6. assets/audio/ep001/ が空になっているか確認")
    print("=" * 60)


if __name__ == "__main__":
    main()

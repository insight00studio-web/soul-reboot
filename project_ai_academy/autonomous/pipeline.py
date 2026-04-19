"""autonomous/pipeline.py - Phase A のメインオーケストレータ。

main() が各 step を順番に呼び出す。Quality Gate（Architect→Writer→Editor）の
リトライループもここに集約している。
"""

import argparse
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from sheets_db import SoulRebootDB
from notifier import notify_success, notify_error

from .architect import step_architect
from .collect import step_collect_analytics, step_collect_news, step_score_comments
from .editor import step_editor
from .memory import write_episode_memory
from .metadata import step_finalize, step_update_metadata
from .utils import _get_story_date_info
from .writer import step_writer

# .envファイルから環境変数を読み込む（プロジェクトルートにある場合）
load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def main():
    parser = argparse.ArgumentParser(description="Soul Reboot 自律生成エンジン")
    parser.add_argument(
        "--episode", type=int, default=None,
        help="生成する話数（省略時はConfigシートの CURRENT_EPISODE を使用）"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="既存の台本データを削除してから再生成する（CURRENT_EPISODEは変更しない）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Soul Reboot - 自律生成エンジン起動")
    print(f"   実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("ERROR: 環境変数 GEMINI_API_KEY が設定されていません")
        print("   set GEMINI_API_KEY=あなたのAPIキー  を実行してください")
        sys.exit(1)

    # DB接続
    # ※ SPREADSHEET_ID は環境変数 または service_account.json と同ディレクトリの .env から取得
    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("ERROR: 環境変数 SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        sys.exit(1)

    db = SoulRebootDB(spreadsheet_id)
    config = db.get_config()

    # 話数の決定
    episode_number = args.episode or int(config.get("CURRENT_EPISODE", 1))
    print(f"\n[EPISODE]: 第{episode_number}話")

    # --force: 既存データを削除してから再生成
    if args.force:
        print(f"\n[FORCE] 第{episode_number}話の既存台本データを削除します...")
        deleted = db.delete_script_lines_by_episode(episode_number)
        print(f"  → {deleted}行削除完了")

    # 各ステップを順番に実行
    current_step = "初期化"
    start_time = time.time()
    try:
        current_step = "ニュース収集"
        news = step_collect_news(db, config)
        current_step = "YouTube Analytics収集"
        analytics_summary = step_collect_analytics(db, config)
        current_step = "コメントスコアリング"
        top_comments = step_score_comments(db)
        current_step = "プロット生成 (Architect)"
        story_date_info = _get_story_date_info(episode_number)
        plot = step_architect(db, config, episode_number, news, top_comments)
        current_step = "台本生成 (Writer)"
        script_lines = step_writer(db, config, episode_number, plot, story_date_info=story_date_info)
        current_step = "台本監修 (Editor)"
        QUALITY_GATE_THRESHOLD = 300
        MAX_RETRY = 1
        for retry in range(MAX_RETRY + 1):
            script_lines, quality_score = step_editor(db, episode_number, plot, script_lines)
            total = quality_score.get("total", 999)
            if total >= QUALITY_GATE_THRESHOLD or retry >= MAX_RETRY:
                if total < QUALITY_GATE_THRESHOLD:
                    print(f"  [QUALITY GATE] スコア{total}点 < {QUALITY_GATE_THRESHOLD}点。リトライ上限に達したため続行。")
                break
            print(f"  [QUALITY GATE] スコア{total}点 < {QUALITY_GATE_THRESHOLD}点。Architectから再生成します（リトライ {retry+1}/{MAX_RETRY}）")
            issues_text = "\n".join(quality_score.get("issues", []))
            plot = step_architect(db, config, episode_number, news, top_comments,
                                  quality_feedback=issues_text)
            script_lines = step_writer(db, config, episode_number, plot, story_date_info=story_date_info)
        current_step = "メタデータ更新"
        step_update_metadata(db, episode_number, plot)
        # Phase 3: 話末状態を narrative/episode_memory/ep_{NN}.yaml に永続化
        # 次話生成時に Architect / Editor が `<previous_episode_state>` として参照する
        try:
            latest_params = db.get_latest_parameters() or {}
            params_for_memory = {
                "trust": int(latest_params.get("信頼度", 0) or 0),
                "awakening": int(latest_params.get("覚醒度", 0) or 0),
                "record": int(latest_params.get("記録度", 0) or 0),
            }
            mem_path = write_episode_memory(
                episode_number, plot, params_for_memory,
                story_date_info=story_date_info,
            )
            if mem_path:
                print(f"  → episode_memory 書き出し: {mem_path}")
        except Exception as e:
            print(f"  WARN: episode_memory 書き出し失敗: {e}（続行）")
        current_step = "完了処理"
        step_finalize(db, episode_number, plot, advance_episode=not args.force, analytics_summary=analytics_summary)
        # 台本の総文字数（セリフ・地の文のみ集計）
        script_char_count = sum(
            len(line.get("セリフ・地の文", "")) for line in script_lines
        )
        notify_success(
            episode_number=episode_number,
            title=plot.get("title", ""),
            cliffhanger=plot.get("cliffhanger", ""),
            elapsed_seconds=time.time() - start_time,
            script_char_count=script_char_count,
        )
        # Phase B 自動トリガー用にエピソード番号を書き出す
        with open("episode_number.txt", "w") as f:
            f.write(str(episode_number))
    except Exception as e:
        notify_error(episode_number=episode_number, step=current_step, error=e)
        raise

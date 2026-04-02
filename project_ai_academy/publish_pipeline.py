"""
publish_pipeline.py
Soul Reboot - Phase B 一括実行パイプライン

台本承認後に以下を順次実行する:
    1. 承認済み台本の確認
    2. アセット生成（TTS音声 + 画像）
    3. 動画編集・MP4書き出し
    4. YouTube予約アップロード（翌朝06:00 JST公開）
    5. 完了メール送信

各ステップでエラーが発生した場合、エラーメールを送信して停止する。

実行コマンド:
    py publish_pipeline.py --episode 1
    py publish_pipeline.py                  # CURRENT_EPISODE - 1 を処理
    py publish_pipeline.py --episode 1 --skip-upload   # YouTube以外を実行
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from sheets_db import SoulRebootDB
from asset_generator import AssetGenerator
from video_compiler import VideoCompiler
from youtube_uploader import YouTubeUploader
from notifier import notify_error, notify_youtube_uploaded, send_notification

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Soul Reboot Phase B パイプライン")
    parser.add_argument("--episode", type=int, help="処理する話数")
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="YouTubeアップロードをスキップする",
    )
    args = parser.parse_args()

    # --- DB接続 ---
    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("ERROR: 環境変数 SOUL_REBOOT_SPREADSHEET_ID が設定されていません")
        sys.exit(1)

    db = SoulRebootDB(spreadsheet_id)
    config = db.get_config()

    # 話数の決定
    current_ep = int(config.get("CURRENT_EPISODE", 2))
    episode_number = args.episode or (current_ep - 1)

    if episode_number < 1:
        print("ERROR: 有効な話数がありません")
        sys.exit(1)

    print("=" * 60)
    print(f"Soul Reboot - Phase B パイプライン 第{episode_number}話")
    print("=" * 60)

    start_time = time.time()
    current_step = "初期化"

    try:
        # --- STEP 1: 承認済み台本の確認 ---
        current_step = "台本確認"
        print(f"\n[STEP 1] 承認済み台本を確認中...")
        scripts = db.get_approved_scripts(episode_number)
        if not scripts:
            raise RuntimeError(
                f"第{episode_number}話の承認済み台本が見つかりません。"
                "スプレッドシートで approved=TRUE に設定してください。"
            )
        print(f"  承認済み台本: {len(scripts)}行")

        # --- STEP 2: アセット生成 ---
        current_step = "アセット生成 (TTS + 画像)"
        print(f"\n[STEP 2] アセット生成中...")
        generator = AssetGenerator(spreadsheet_id)
        generator.process_episode(episode_number)
        print("  アセット生成完了")

        # --- STEP 3: 動画編集・書き出し ---
        current_step = "動画編集・書き出し"
        print(f"\n[STEP 3] 動画を書き出し中...")
        compiler = VideoCompiler(spreadsheet_id)
        video_path = compiler.compile_episode(episode_number)
        print(f"  動画書き出し完了: {video_path}")

        # --- STEP 3.5: サムネイル生成 ---
        episode_info = db.get_episode(episode_number)
        title = episode_info.get("タイトル案", f"第{episode_number}話")
        video_title = f"【Soul Reboot】第{episode_number}話「{title}」"
        cliffhanger = episode_info.get("クリフハンガー", "")

        current_step = "サムネイル生成"
        print(f"\n[STEP 3.5] サムネイル生成中...")
        scene1_image = str(
            Path(__file__).parent / "assets" / "images"
            / f"ep{episode_number:03d}" / f"ep{episode_number:03d}_sc01.png"
        )
        thumbnail_path = generator.generate_thumbnail(
            ep_num=episode_number,
            title=title,
            base_image_path=scene1_image,
        )
        if thumbnail_path:
            print(f"  サムネイル生成完了: {thumbnail_path}")
            db.register_asset(
                episode_number=episode_number,
                scene_number=0,
                asset_type="THUMBNAIL",
                file_path=thumbnail_path,
            )
        else:
            print("  WARN: サムネイル生成失敗（スキップ）")

        # --- STEP 4: YouTube アップロード ---
        description = _build_description(episode_number, title, cliffhanger)

        video_id = ""
        youtube_url = ""
        if args.skip_upload:
            print(f"\n[STEP 4] YouTubeアップロードをスキップ")
        else:
            current_step = "YouTubeアップロード"
            print(f"\n[STEP 4] YouTubeにアップロード中...")
            uploader = YouTubeUploader()
            video_id, youtube_url = uploader.upload(
                video_path=video_path,
                title=video_title,
                description=description,
            )
            print(f"  YouTube URL: {youtube_url}")

            # サムネイル設定
            if video_id and thumbnail_path:
                current_step = "サムネイル設定"
                print(f"\n[STEP 4.5] サムネイルを設定中...")
                uploader.set_thumbnail(video_id, thumbnail_path)

        # --- STEP 5: 完了通知 ---
        current_step = "完了通知"
        elapsed = time.time() - start_time
        mins, secs = divmod(int(elapsed), 60)

        if youtube_url:
            notify_youtube_uploaded(episode_number, video_title, youtube_url)
        else:
            # アップロードスキップ時は汎用通知
            send_notification(
                subject=f"[完了] Soul Reboot 第{episode_number}話 動画書き出し完了",
                body=(
                    f"第{episode_number}話 動画書き出し完了\n\n"
                    f"タイトル: {video_title}\n"
                    f"動画ファイル: {video_path}\n"
                    f"作業時間: {mins}分{secs}秒\n\n"
                    "YouTubeアップロードはスキップされました。"
                ),
            )

        print("\n" + "=" * 60)
        print(f"DONE: 第{episode_number}話 Phase B 完了（{mins}分{secs}秒）")
        if youtube_url:
            print(f"  YouTube: {youtube_url}")
        print(f"  動画: {video_path}")
        print("=" * 60)

    except Exception as e:
        notify_error(episode_number=episode_number, step=current_step, error=e)
        print(f"\nERROR [{current_step}]: {e}")
        raise


def _build_description(episode_number: int, title: str, cliffhanger: str) -> str:
    """YouTube動画の説明文を構築する"""
    lines = [
        f"Soul Reboot 第{episode_number}話「{title}」",
        "",
        "AIが100日間、毎日自動で物語を紡ぐ実験的プロジェクト。",
        "ナギサとシンジの運命は、あなたのコメントで変わる。",
        "",
    ]
    if cliffhanger:
        lines.append(f"今話のクライマックス: {cliffhanger}")
        lines.append("")
    lines.extend([
        "---",
        "この動画はAI技術（Gemini / Claude）を活用して制作しています。",
        "映像・音声はAI生成、ストーリーはAIが自律的に生成し人間が監修しています。",
        "This video features AI-generated visuals, voices, and story content.",
        "",
        "#SoulReboot #AI生成アニメ #連載 #物語",
        "",
        "チャンネル登録・コメントお願いします！",
        "あなたのコメントが物語に影響を与えます。",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    main()

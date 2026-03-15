"""
setup_spreadsheet.py
Soul Reboot - スプレッドシートの初期化スクリプト

【実行手順】
1. Google Cloud Consoleで OAuth2クライアントID（デスクトップアプリ型）を作成し、
   credentials.json をこのファイルと同じフォルダに保存する。
2. 環境変数を設定:
       set SOUL_REBOOT_SPREADSHEET_ID=あなたのスプレッドシートID
3. このスクリプトを実行（初回はブラウザが開く）:
       python setup_spreadsheet.py

実行後、スプレッドシートに9枚のシートと見出し行が自動で作成されます。
"""

import os
import sys
import time
import gspread

# ===================================================================
# 設定
# ===================================================================

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token.json")

# ===================================================================
# 各シートの定義（シート名: [ヘッダー列リスト]）
# ===================================================================

SHEETS = {
    "📋 Episodes": [
        "話数", "公開日", "物語内の日数", "フェーズ", "タイトル案",
        "確定タイトル", "この話の目的", "感情曲線", "プロット要約",
        "クリフハンガー", "ステータス", "YouTube_URL", "メモ",
    ],
    "📜 Scripts": [
        "話数", "シーン番号", "シーン名", "画像プロンプト",
        "話者", "セリフ・地の文", "感情トーン", "音声キャラ",
        "音声ファイルパス", "承認済", "メモ",
    ],
    "🔮 Foreshadowing": [
        "伏線ID", "追加話数", "伏線内容", "回収予定話数",
        "確定回収話数", "ステータス", "回収済話数", "回収メモ",
        "重要度",
    ],
    "💬 Comments": [
        "収集日", "対象話数", "コメントID", "投稿者名",
        "コメント本文", "いいね数", "AI感情分析", "採用スコア",
        "採用ステータス", "採用話数", "採用方法",
        "手動上書き", "メモ",
    ],
    "📊 Parameters": [
        "話数", "信頼度", "覚醒度", "記録度",
        "信頼度変化", "覚醒度変化", "記録度変化",
        "変動トリガー", "分岐フラグ", "手動調整", "メモ",
    ],
    "🎵 Assets": [
        "アセットID", "話数", "シーン番号", "アセット種類",
        "ファイルパス", "生成プロンプト", "生成日時", "承認済",
        "再生成指示", "メモ",
    ],
    "📰 News": [
        "取得日", "見出し", "情報ソース", "カテゴリ",
        "関連スコア", "採用話数", "採用方法", "承認済",
    ],
    "📖 Memory_L2": [
        "話数", "タイトル", "要約", "未回収の伏線",
        "シンジの状態", "ナギサの状態", "話の終わりの信頼値", "話の終わりの覚醒値",
    ],
    "⚙️ Config": [
        "設定キー", "設定値", "説明",
    ],
}

# Configシートの初期値
CONFIG_INITIAL_DATA = [
    ["CURRENT_EPISODE",           "1",             "今日生成する話数"],
    ["PHASE",                     "PHASE_1",       "現在のフェーズ（PHASE_1/PHASE_2）"],
    ["AUTO_PUBLISH",              "FALSE",         "自動YouTube投稿（FALSE=手動承認が必要）"],
    ["COMMENT_FETCH_COUNT",       "50",            "毎日収集するコメント数"],
    ["NEWS_FETCH_COUNT",          "5",             "毎日収集するニュース数"],
    ["GEMINI_MODEL",              "gemini-2.5-flash", "使用するGeminiモデル"],
    ["PARAMETER_UPDATE_MODE",     "AUTO",          "AUTO=AI自動更新 / MANUAL=手動更新"],
    ["REAL_DATE_OFFSET_DAYS",     "0",             "現実日付と物語日付のオフセット（日数）"],
    ["SPREADSHEET_ID",            "",              "このスプレッドシートのID（参照用）"],
]

# Parametersシートの初期値（第0話＝物語開始前の基準値）
PARAMETERS_INITIAL_DATA = [
    ["0", "20", "0", "5", "0", "0", "0", "初期値", "", "FALSE", "物語開始前の基準パラメータ"],
]

# ===================================================================
# ヘルパー関数
# ===================================================================

def set_header_style(ws: gspread.Worksheet) -> None:
    """ヘッダー行を太字・背景色グレーに整形する（gspread batch_update使用）"""
    spreadsheet = ws.spreadsheet
    sheet_id = ws.id
    num_cols = ws.col_count

    body = {
        "requests": [
            # ヘッダー行を太字に
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.85, "green": 0.90, "blue": 0.95
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            },
            # ヘッダー行を固定（スクロールしても見える）
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ]
    }
    spreadsheet.batch_update(body)


# ===================================================================
# メイン処理
# ===================================================================

def main():
    spreadsheet_id = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID", "")
    if not spreadsheet_id:
        print("❌ エラー: 環変数 SOUL_REBOOT_SPREADSHEET_ID を設定してください")
        print("   例: set SOUL_REBOOT_SPREADSHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms")
        sys.exit(1)

    print("=" * 60)
    print("🛠️  Soul Reboot - スプレッドシート初期化開始")
    print("=" * 60)

    # OAuth2認証（初回はブラウザでログイン、以降は token.json を自動使用）
    print("🔑 Googleアカウント認証中... (初回はブラウザが開きます)")
    client = gspread.oauth(
        credentials_filename=CREDENTIALS_FILE,
        authorized_user_filename=TOKEN_FILE,
    )
    spreadsheet = client.open_by_key(spreadsheet_id)
    print(f"✅ スプレッドシート接続: {spreadsheet.title}")

    # 既存シートのタイトル一覧を取得
    existing_sheets = {ws.title for ws in spreadsheet.worksheets()}

    for sheet_name, headers in SHEETS.items():
        print(f"\n📄 シート作成中: {sheet_name}")

        if sheet_name in existing_sheets:
            ws = spreadsheet.worksheet(sheet_name)
            print(f"   ⚠️ 既に存在します。ヘッダーのみ確認・修正します")
        else:
            # 行数・列数を適切に設定して新規作成
            ws = spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=len(headers) + 2
            )
            print(f"   ✅ 新規作成しました")

        # ヘッダーを書き込む
        ws.update([headers], "A1")

        # Configシートのみ初期データを挿入
        if sheet_name == "⚙️ Config":
            if ws.row_count < 2 or not ws.cell(2, 1).value:
                ws.append_rows(CONFIG_INITIAL_DATA)
                print(f"   ✅ 初期設定値を書き込みました")

        # Parametersシートのみ初期データを挿入
        if sheet_name == "📊 Parameters":
            if ws.row_count < 2 or not ws.cell(2, 1).value:
                ws.append_rows(PARAMETERS_INITIAL_DATA)
                print(f"   ✅ 初期パラメータを書き込みました")

        # ヘッダー行をスタイリング
        try:
            set_header_style(ws)
            print(f"   ✅ ヘッダースタイルを適用しました")
        except Exception as e:
            print(f"   ⚠️ スタイル適用失敗（機能には影響なし）: {e}")

        # API制限対策
        time.sleep(0.5)

    # 最初から存在するシート「シート1」を削除（存在する場合のみ）
    for ws in spreadsheet.worksheets():
        if ws.title in ("Sheet1", "シート1"):
            spreadsheet.del_worksheet(ws)
            print(f"\n🗑️ デフォルトシート「{ws.title}」を削除しました")
            break

    # ConfigにスプレッドシートIDを書き込む
    try:
        config_ws = spreadsheet.worksheet("⚙️ Config")
        cell = config_ws.find("SPREADSHEET_ID", in_column=1)
        if cell:
            config_ws.update_cell(cell.row, 2, spreadsheet_id)
            print(f"\n✅ ConfigにスプレッドシートIDを書き込みました")
    except Exception as e:
        print(f"\n⚠️ SPREADSHEET_ID の書き込みに失敗: {e}")

    print("\n" + "=" * 60)
    print("🎉 スプレッドシートの初期化が完了しました！")
    print(f"\n📎 スプレッドシートURL:")
    print(f"   https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
    print("\n📋 次のステップ:")
    print("   1. [⚙️ Config] シートで設定値を確認してください")
    print("   2. 環境変数 GEMINI_API_KEY を設定してください")
    print("   3. python autonomous_engine.py  を実行してください")
    print("=" * 60)


if __name__ == "__main__":
    main()

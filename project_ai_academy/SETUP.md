# Soul Reboot - セットアップガイド（OAuth2版）

## 必要なライブラリのインストール

```powershell
pip install gspread google-auth-oauthlib google-generativeai
```

---

## Google Cloud の設定（初回のみ・約5分）

### 1. プロジェクトの作成とAPIの有効化

1. [Google Cloud Console](https://console.cloud.google.com/) を開く
2. 上部の **「プロジェクトを選択」→「新しいプロジェクト」** を作成
   - 名前例: `soul-reboot`
3. 左メニュー → **「APIとサービス」→「ライブラリ」**
4. 以下の **2つ** を検索して有効化:
   - `Google Sheets API` → 有効にする
   - `Google Drive API` → 有効にする

### 2. OAuth2 クライアントIDの作成

1. 左メニュー → **「APIとサービス」→「認証情報」**
2. **「認証情報を作成」→「OAuth クライアント ID」**
3. **「同意画面を設定」** が求められる場合:
   - ユーザータイプ: **「外部」** を選択
   - アプリ名: `Soul Reboot`（なんでも可）
   - メールアドレスを入力 → 保存して次へ（スコープ等はスキップして完了）
4. **アプリケーションの種類: 「デスクトップアプリ」** を選択
5. 名前: `soul-reboot-client`
6. **「作成」** → **「JSONをダウンロード」**
7. ダウンロードしたファイルを **`credentials.json`** という名前で以下に保存:

```text
c:\Users\uca-n\youtube\project_ai_academy\credentials.json
```

---

## スプレッドシートの作成

1. [Google スプレッドシート](https://sheets.google.com) で **新規作成**
2. URLが以下のような形式になる:

   ```text
   https://docs.google.com/spreadsheets/d/【ここがID】/edit
   ```

3. この **スプレッドシートID** をコピーしておく

> ✅ **OAuth2方式では「共有設定」は不要です。**
> 自分のGoogleアカウントでログインするため、自分のドライブにあるシートはそのまま使えます。

---

## 環境変数の設定

PowerShellで以下を実行（**毎回必要** または システム環境変数に恒久登録推奨）:

```powershell
$env:GEMINI_API_KEY = "あなたのGemini APIキー"
$env:SOUL_REBOOT_SPREADSHEET_ID = "あなたのスプレッドシートID"
$env:GMAIL_ADDRESS = "あなたのGmailアドレス"
$env:GMAIL_APP_PASSWORD = "アプリパスワード16文字"
```

### 恒久的に設定する場合（推奨）

```powershell
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "あなたのAPIキー", "User")
[System.Environment]::SetEnvironmentVariable("SOUL_REBOOT_SPREADSHEET_ID", "あなたのID", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL_ADDRESS", "あなたのGmailアドレス", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL_APP_PASSWORD", "アプリパスワード16文字", "User")
```

### Gmail アプリパスワードの取得手順

1. [Googleアカウント](https://myaccount.google.com/) → **「セキュリティ」**
2. **「2段階認証プロセス」** を有効化（未設定の場合）
3. 同ページ内の検索欄で **「アプリパスワード」** を検索
4. アプリ名を任意で入力 → **「作成」** → 16文字のパスワードが表示される
5. その16文字を `GMAIL_APP_PASSWORD` に設定する

設定後、**PowerShellを再起動** すると有効になります。

---

## スプレッドシートの初期化（初回のみ）

```powershell
cd c:\Users\uca-n\youtube\project_ai_academy
python setup_spreadsheet.py
```

**初回実行時**: ブラウザが自動で開き、Googleアカウントのログイン画面が表示されます。

- ログインして許可を押すと、`token.json` が自動保存されます
- **2回目以降はブラウザ不要** で完全自動で動きます

実行後、スプレッドシートに **9枚のシート** が自動作成されます。

---

## 毎日の実行

```powershell
cd c:\Users\uca-n\youtube\project_ai_academy
python autonomous_engine.py
```

特定の話数を指定:

```powershell
python autonomous_engine.py --episode 5
```

---

## ファイル構成

```text
project_ai_academy/
├── autonomous_engine.py      # メインエンジン（毎日実行）
├── sheets_db.py              # Google Sheets DB アクセス層
├── setup_spreadsheet.py      # スプレッドシート初期化（初回のみ）
├── credentials.json          # ← Google CloudからDL（Gitに含めないこと！）
├── token.json                # ← 初回ログイン後に自動生成（Gitに含めないこと！）
├── project_design.md         # プロジェクト設計書
├── spreadsheet_db_design.md  # スプレッドシートDB設計書
├── SETUP.md                  # このファイル
├── prompts/
│   ├── architect_prompt.md   # Architect AI指示書
│   └── writer_prompt.md      # Writer AI指示書
└── episodes/
    ├── ep001_plot.json        # 第1話プロット
    └── ep001_script.txt       # 第1話台本（手書き版）
```

---

## 毎日の確認フロー（あなたの作業）

エンジン実行後、スプレッドシートで以下を確認・修正します:

| シート | 確認内容 | アクション |
| --- | --- | --- |
| `📋 Episodes` | タイトル・プロット | `title_final` 欄を編集して確定 |
| `📜 Scripts` | 台本のセリフ全文 | `approved` を `TRUE` に変更 |
| `💬 Comments` | 採用候補コメント | `manual_override` で調整 |
| `🔮 Foreshadowing` | 伏線の回収時期 | `target_episode_final` を手動修正 |
| `⚙️ Config` | 各種設定値 | 必要に応じて変更 |

---

> ⚠️ 以下のファイルは **絶対に Git にコミットしないこと**
> `.gitignore` に追加してください:
>
> ```text
> credentials.json
> token.json
> ```

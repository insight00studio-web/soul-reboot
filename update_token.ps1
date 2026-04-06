# Soul Reboot - GitHub Secret Token Update Script
# Run this every day before JST 01:00

# .env からスプレッドシートIDを自動読み込み
$envFile = "$PSScriptRoot\project_ai_academy\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$credsPath = "$env:USERPROFILE\.claude\.credentials.json"

if (-not (Test-Path $credsPath)) {
    Write-Host "ERROR: Credentials file not found: $credsPath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "=== Soul Reboot Token Update ===" -ForegroundColor Cyan

# claude コマンドで API コールを行い、トークンを強制リフレッシュする
Write-Host "Refreshing Claude token..." -ForegroundColor Yellow
$claudeOutput = claude -p "ok" --output-format text 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Token refreshed." -ForegroundColor Green
} else {
    Write-Host "WARN: Token refresh failed. Using existing token." -ForegroundColor Yellow
}

# リフレッシュ後に credentials.json を読み直す
$creds = Get-Content $credsPath | ConvertFrom-Json
$token = $creds.claudeAiOauth.accessToken
$expiresAt = $creds.claudeAiOauth.expiresAt

if (-not $token) {
    Write-Host "ERROR: Token not found. Please launch Claude Code first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$expiryDate = [DateTimeOffset]::FromUnixTimeMilliseconds($expiresAt).LocalDateTime
$now = Get-Date
$remainingHours = [math]::Round(($expiryDate - $now).TotalHours, 1)

Write-Host "Token : $($token.Substring(0, 30))..."
Write-Host "Expiry: $($expiryDate.ToString('yyyy/MM/dd HH:mm')) ($remainingHours hours remaining)"

if ($remainingHours -lt 2) {
    Write-Host "WARNING: Token expires in less than 2 hours. Please launch Claude Code first." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "Updating GitHub Secret..." -ForegroundColor Yellow
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo insight00studio-web/soul-reboot --body $token

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: CLAUDE_CODE_OAUTH_TOKEN updated." -ForegroundColor Green
} else {
    Write-Host "ERROR: CLAUDE_CODE_OAUTH_TOKEN update failed. Make sure gh command is installed." -ForegroundColor Red
}

# --- Google Token Update ---
Write-Host ""
Write-Host "=== Google Token Update ===" -ForegroundColor Cyan

$googleTokenPath = "$PSScriptRoot\project_ai_academy\token.json"

if (-not (Test-Path $googleTokenPath)) {
    Write-Host "ERROR: token.json not found: $googleTokenPath" -ForegroundColor Red
    Write-Host "Run the following to authenticate:" -ForegroundColor Yellow
    Write-Host "  cd project_ai_academy" -ForegroundColor Yellow
} else {
    Write-Host "Refreshing Google token..." -ForegroundColor Yellow
    $env:PYTHONPATH = "$PSScriptRoot\project_ai_academy"
    Push-Location "$PSScriptRoot\project_ai_academy"
    python -c "
import os, sys
sys.path.insert(0, '.')
sid = os.environ.get('SOUL_REBOOT_SPREADSHEET_ID')
if not sid:
    print('WARN: SOUL_REBOOT_SPREADSHEET_ID not set. Skipping refresh.')
    sys.exit(0)
from sheets_db import SoulRebootDB
SoulRebootDB(sid)
print('Token refresh OK')
" 2>&1
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Uploading token.json to GitHub Secret..." -ForegroundColor Yellow
        $googleToken = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content $googleTokenPath -Raw)))
        gh secret set GOOGLE_TOKEN_JSON --repo insight00studio-web/soul-reboot --body $googleToken
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: GOOGLE_TOKEN_JSON updated." -ForegroundColor Green
        } else {
            Write-Host "ERROR: GOOGLE_TOKEN_JSON update failed." -ForegroundColor Red
        }
    } else {
        Write-Host "ERROR: Google token refresh failed. Re-authentication may be required." -ForegroundColor Red
    }
}

# --- YouTube Token Update ---
Write-Host ""
Write-Host "=== YouTube Token Check ===" -ForegroundColor Cyan

$youtubeTokenPath = "$PSScriptRoot\project_ai_academy\youtube_token.json"

if (-not (Test-Path $youtubeTokenPath)) {
    Write-Host "WARN: youtube_token.json not found. YOUTUBE_TOKEN_JSON not updated." -ForegroundColor Yellow
    Write-Host "  Run: cd project_ai_academy && python yt_reauth.py credentials.json youtube_token.json" -ForegroundColor Yellow
} else {
    # トークン期限確認
    Push-Location "$PSScriptRoot\project_ai_academy"
    $ytExpiryInfo = python yt_check_expiry.py 2>&1
    Pop-Location

    $ytDaysLine = $ytExpiryInfo | Where-Object { $_ -match "^DAYS:" }
    $ytExpiry = if ($ytDaysLine) { $ytDaysLine -replace "^DAYS:", "" } else { "unknown" }
    Write-Host "YouTube token days remaining: $ytExpiry"

    # リフレッシュトークン有効性チェック
    Push-Location "$PSScriptRoot\project_ai_academy"
    $ytCheckResult = python yt_check_token.py 2>&1
    Pop-Location

    if ($ytCheckResult -match "^INVALID") {
        Write-Host "WARNING: YouTube refresh token is invalid. Re-authenticating..." -ForegroundColor Red
        Write-Host "  Browser will open. Please login with your Google account." -ForegroundColor Yellow
        $reAuthScript = "$PSScriptRoot\project_ai_academy\yt_reauth.py"
        $credentialsPath = "$PSScriptRoot\project_ai_academy\credentials.json"
        $tokenOutPath = "$PSScriptRoot\project_ai_academy\youtube_token.json"
        python $reAuthScript $credentialsPath $tokenOutPath 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: YouTube re-authentication complete." -ForegroundColor Green
        } else {
            Write-Host "ERROR: YouTube re-authentication failed." -ForegroundColor Red
            Write-Host "  Manual: cd project_ai_academy && python yt_reauth.py credentials.json youtube_token.json" -ForegroundColor Yellow
        }
    } elseif ($ytCheckResult -match "^REFRESHED") {
        Write-Host "OK: YouTube access token refreshed." -ForegroundColor Green
    } else {
        Write-Host "OK: YouTube token is valid." -ForegroundColor Green
    }

    Write-Host "Uploading youtube_token.json to GitHub Secret..." -ForegroundColor Yellow
    $youtubeToken = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content $youtubeTokenPath -Raw)))
    gh secret set YOUTUBE_TOKEN_JSON --repo insight00studio-web/soul-reboot --body $youtubeToken
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: YOUTUBE_TOKEN_JSON updated." -ForegroundColor Green
    } else {
        Write-Host "ERROR: YOUTUBE_TOKEN_JSON update failed." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "All done! Phase A runs automatically at 01:00 JST." -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit"

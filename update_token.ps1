# Soul Reboot - GitHub Secret Token Update Script
# Run this every evening before 23:00 JST

$credsPath = "$env:USERPROFILE\.claude\.credentials.json"

if (-not (Test-Path $credsPath)) {
    Write-Host "ERROR: Credentials file not found: $credsPath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

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

Write-Host ""
Write-Host "=== Soul Reboot Token Update ===" -ForegroundColor Cyan
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
    Write-Host "  python -c `"from sheets_db import SoulRebootDB; import os; SoulRebootDB(os.environ['SOUL_REBOOT_SPREADSHEET_ID'])`"" -ForegroundColor Yellow
} else {
    Write-Host "Refreshing Google token..." -ForegroundColor Yellow
    $env:PYTHONPATH = "$PSScriptRoot\project_ai_academy"
    $spreadsheetId = (gh secret list --repo insight00studio-web/soul-reboot --json name | ConvertFrom-Json | Where-Object { $_.name -eq "SOUL_REBOOT_SPREADSHEET_ID" } | Select-Object -First 1)
    # token.json のアクセストークンをリフレッシュするため Python で接続テスト
    Push-Location "$PSScriptRoot\project_ai_academy"
    python -c "
import os, sys
sys.path.insert(0, '.')
sid = os.environ.get('SOUL_REBOOT_SPREADSHEET_ID')
if not sid:
    print('WARN: SOUL_REBOOT_SPREADSHEET_ID not set in environment. Skipping refresh.')
    sys.exit(0)
from sheets_db import SoulRebootDB
SoulRebootDB(sid)
print('Token refresh OK')
" 2>&1
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Uploading token.json to GitHub Secret..." -ForegroundColor Yellow
        $googleToken = Get-Content $googleTokenPath -Raw
        $googleToken | gh secret set GOOGLE_TOKEN_JSON --repo insight00studio-web/soul-reboot --body -
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: GOOGLE_TOKEN_JSON updated." -ForegroundColor Green
        } else {
            Write-Host "ERROR: GOOGLE_TOKEN_JSON update failed." -ForegroundColor Red
        }
    } else {
        Write-Host "ERROR: Google token refresh failed. Re-authentication may be required." -ForegroundColor Red
        Write-Host "Run manually: cd project_ai_academy && python -c `"from sheets_db import SoulRebootDB; import os; SoulRebootDB(os.environ['SOUL_REBOOT_SPREADSHEET_ID'])`"" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "All done! Phase A runs automatically at 00:00 JST." -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit"

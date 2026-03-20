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
    Write-Host "OK: Update complete! Phase A runs automatically at 00:00 JST." -ForegroundColor Green
} else {
    Write-Host "ERROR: Update failed. Make sure gh command is installed." -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"

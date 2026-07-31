# Run on the Windows PC that can reach 192.168.128.178
# Usage:
#   $env:DISCORD_WEBHOOK_TEST = 'https://discord.com/api/webhooks/...'
#   powershell -ExecutionPolicy Bypass -File tools\yokuumakun_netkeiba_access_test\deploy_from_windows.ps1

$ErrorActionPreference = "Stop"
if (-not $env:DISCORD_WEBHOOK_TEST) {
  Write-Error "Set DISCORD_WEBHOOK_TEST first."
}
$py = @(
  "$env:LOCALAPPDATA\Python\bin\python3.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "python"
) | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& $py "$scriptDir\deploy_paramiko.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Deploy finished."

# Run on the Windows PC that can reach 192.168.128.178
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\yokuumakun_tenkai_sim_launch\deploy_from_windows.ps1

$ErrorActionPreference = "Stop"
$py = @(
  "$env:LOCALAPPDATA\Python\bin\python3.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "python"
) | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Using python: $py"
Write-Host "Source candidates: Desktop\yokuumakun (or `$env:YOKUMAKUN_SIM_SOURCE)"
& $py "$scriptDir\deploy_paramiko.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Deploy finished. Check admin_api.json for tenkai_sim_url_template."

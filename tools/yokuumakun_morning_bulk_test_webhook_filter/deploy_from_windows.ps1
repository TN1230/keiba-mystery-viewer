# LAN 上の Windows からサーバへ morning_bulk TEST_ALWAYS フィルタを入れる
# 例:
#   powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python deploy_paramiko.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "DONE"

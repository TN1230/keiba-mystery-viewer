# LAN の Windows から自宅サーバーへ SSH インターネット公開を入れる
# 例:
#   powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python deploy_paramiko.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "DONE: check https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json"

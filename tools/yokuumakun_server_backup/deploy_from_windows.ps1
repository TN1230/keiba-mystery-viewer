# Run on the Windows PC that can reach 192.168.128.178
# Backs up /opt/yokuumakun_auto-x into the weekly backup destination on the server.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python deploy_paramiko.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-Content "_deploy_server_backup_out.txt" -ErrorAction SilentlyContinue

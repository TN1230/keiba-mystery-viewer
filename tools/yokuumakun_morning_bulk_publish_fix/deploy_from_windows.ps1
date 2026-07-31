$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python deploy_paramiko.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "DONE"

# 先週まで成功していた Windows LAN + paramiko 方式で閲覧サイトを強制公開
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = $null
foreach ($c in @(
    "$env:LOCALAPPDATA\Python\bin\python3.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "python",
    "py"
)) {
    try {
        $v = & $c -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { $py = $v.Trim(); break }
    } catch {}
}
if (-not $py) { throw "python not found" }

& $py -m pip install -q paramiko
& $py .\deploy_paramiko.py
exit $LASTEXITCODE

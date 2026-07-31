#!/usr/bin/env python3
"""Deploy netkeiba access test into yokuumakun_auto-x via SSH/paramiko."""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("paramiko が必要です: pip install paramiko", file=sys.stderr)
    raise SystemExit(2)

HERE = Path(__file__).resolve().parent
SSH_HOST = os.environ.get("YOKUU_SSH_HOST", "192.168.128.178")
SSH_USER = os.environ.get("YOKUU_SSH_USER", "tn")
REMOTE_ROOT = os.environ.get("YOKUU_ROOT", "/opt/yokuumakun_auto-x")
CREDS_CANDIDATES = [
    Path(os.environ["YOKUU_CREDS_FILE"]) if os.environ.get("YOKUU_CREDS_FILE") else None,
    Path(r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt"),
    Path.home() / "ローカルサーバーIP.txt",
]


def _read_password() -> str:
    env = os.environ.get("YOKUU_SSH_PASS") or os.environ.get("SSH_PASS")
    if env:
        return env.strip()
    for p in CREDS_CANDIDATES:
        if p and p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"(?im)^pass:\s*(\S+)\s*$", text) or re.search(
                r"(?im)^password:\s*(\S+)\s*$", text
            )
            if m:
                return m.group(1).strip()
    raise RuntimeError("SSH パスワードが見つかりません（YOKUU_SSH_PASS または認証ファイル）")


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def main() -> int:
    pw = _read_password()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        SSH_HOST,
        username=SSH_USER,
        password=pw,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    sftp = client.open_sftp()
    remote_dir = f"{REMOTE_ROOT}/_netkeiba_access_install"
    try:
        sftp.mkdir(remote_dir)
    except OSError:
        pass
    for name in ("netkeiba_access_test.py", "install_into_admin_panel.py"):
        local = HERE / name
        remote = f"{remote_dir}/{name}"
        sftp.put(str(local), remote)
        print("uploaded", remote)
    sftp.close()

    cmds = [
        f"cp {remote_dir}/netkeiba_access_test.py {REMOTE_ROOT}/netkeiba_access_test.py",
        f"cp {remote_dir}/install_into_admin_panel.py {remote_dir}/install_into_admin_panel.py",
        f"cd {remote_dir} && python3 install_into_admin_panel.py {REMOTE_ROOT}",
        f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile netkeiba_access_test.py admin_panel_api.py && echo COMPILE_OK",
        # Webhook: 環境変数 DISCORD_WEBHOOK_TEST があれば .env に反映
        (
            "python3 - <<'PY'\n"
            "import os\n"
            "from pathlib import Path\n"
            f"p=Path('{REMOTE_ROOT}/.env')\n"
            "wh=(os.environ.get('DISCORD_WEBHOOK_TEST') or '').strip()\n"
            "text=p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''\n"
            "lines=text.splitlines()\n"
            "if wh:\n"
            "    out=[]; done=False\n"
            "    for line in lines:\n"
            "        if line.startswith('DISCORD_WEBHOOK_TEST='):\n"
            "            out.append('DISCORD_WEBHOOK_TEST='+wh); done=True\n"
            "        else: out.append(line)\n"
            "    if not done: out.append('DISCORD_WEBHOOK_TEST='+wh)\n"
            "    p.write_text('\\n'.join(out)+'\\n', encoding='utf-8')\n"
            "    print('env_webhook=updated')\n"
            "elif not any(l.startswith('DISCORD_WEBHOOK_TEST=') for l in lines):\n"
            "    p.write_text(text.rstrip()+'\\n# DISCORD_WEBHOOK_TEST=https://discord.com/api/webhooks/...\\n', encoding='utf-8')\n"
            "    print('env_webhook=placeholder')\n"
            "else:\n"
            "    print('env_webhook=kept')\n"
            "PY"
        ),
        f"echo '{pw}' | sudo -S systemctl restart yokuum-admin-panel.service",
        "sleep 1",
        "systemctl is-active yokuum-admin-panel.service",
        "curl -sS http://127.0.0.1:8791/health",
        (
            f"cd {REMOTE_ROOT} && YOKUMAKUN_ROOT={REMOTE_ROOT} "
            ".venv/bin/python -c \"from netkeiba_access_test import run_netkeiba_access_test;"
            "import json; r=run_netkeiba_access_test(); print(json.dumps({k:r.get(k) for k in "
            "('ok','denied','race_id','webhook')}, ensure_ascii=False))\""
        ),
    ]
    rc = 0
    for cmd in cmds:
        code, out = _run(client, cmd)
        safe = out.replace(pw, "***")
        print(f"=== exit={code} ===\n{safe}\n")
        if code != 0 and "COMPILE_OK" in cmd:
            rc = code
        if code != 0 and "install_into_admin_panel" in cmd:
            rc = code
    client.close()
    return rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        raise SystemExit(1)

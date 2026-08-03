#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows LAN からサーバ状態だけ確認（適用なし・Cloud Agent 不使用）。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required: pip install paramiko") from None

RESULT_FILE = Path(__file__).with_name("_status_lan_ops_out.txt")


def _password() -> str:
    env = (
        os.environ.get("YOKUMAKUN_SSH_PASS")
        or os.environ.get("YOKUU_SSH_PASS")
        or os.environ.get("SSHPASS")
        or ""
    ).strip()
    if env and env not in {"…", "..."}:
        return env
    for cand in (
        os.environ.get("YOKUMAKUN_SSH_CREDS", ""),
        r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt",
        r"C:\Users\user\Desktop\ローカルサーバーIP.txt",
        str(Path.home() / "Desktop" / "ローカルサーバーIP.txt"),
    ):
        if not cand:
            continue
        p = Path(cand)
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?im)^pass:\s*(\S+)\s*$", text) or re.search(
            r"(?im)^password:\s*(\S+)\s*$", text
        )
        if m:
            return m.group(1).strip()
    raise RuntimeError("password not found in YOKUMAKUN_SSH_PASS or ローカルサーバーIP.txt")


def main() -> int:
    host = (
        os.environ.get("YOKUMAKUN_SSH_HOST")
        or os.environ.get("YOKUU_SSH_HOST")
        or "192.168.128.178"
    )
    user = (
        os.environ.get("YOKUMAKUN_SSH_USER")
        or os.environ.get("YOKUU_SSH_USER")
        or "tn"
    )
    pw = _password()
    lines: list[str] = []

    def log(msg: str) -> None:
        safe = msg.replace(pw, "***")
        lines.append(safe)
        print(safe, flush=True)

    cmd = """
set -e
echo "==== host ===="
hostname; whoami; TZ=Asia/Tokyo date -Iseconds
echo "==== automation ===="
systemctl is-active yokuum-server-automation-x.service 2>&1 || true
systemctl is-enabled yokuum-server-automation-x.service 2>&1 || true
echo "==== race-day timers ===="
systemctl list-timers 'yokuum-race-day-*' 'yokuum-morning-publish-watch.timer' --no-pager 2>&1 || true
echo "==== crontab ===="
crontab -l 2>/dev/null | grep -nE 'CRON_TZ|race_day_|evening_functional|preflight|publish' || true
echo "==== latest.json head ===="
python3 - <<'PY'
from pathlib import Path
p=Path('/opt/yokuumakun_auto-x/public_viewer/snapshots/latest.json')
print(p if p.is_file() else 'missing', (p.read_text(encoding='utf-8', errors='replace')[:300] if p.is_file() else ''))
PY
""".strip()

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        log(f"connect {user}@{host} …")
        client.connect(
            host,
            username=user,
            password=pw,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=30,
            auth_timeout=30,
        )
        _, stdout, stderr = client.exec_command(cmd, timeout=120)
        out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        log(out)
        log(f"remote_rc={rc}")
        client.close()
        log("RESULT: SUCCESS" if rc == 0 else "RESULT: FAILED")
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0 if rc == 0 else 1
    except Exception as e:
        log(f"RESULT: FAILED\n{type(e).__name__}: {e}")
        if "Connection reset" in str(e) or "timed out" in str(e).lower():
            log("HINT: run this on the home Windows PC on the same LAN (not Cloud Agent).")
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

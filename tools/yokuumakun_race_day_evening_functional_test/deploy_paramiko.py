#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows LAN から自宅サーバーへ 21:00 機能テストを配置する。"""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required: pip install paramiko") from None

REMOTE_ROOT = "/opt/yokuumakun_auto-x"
LOCAL_DIR = Path(__file__).resolve().parent
RESULT_FILE = Path(__file__).with_name("_deploy_eod_func_test_out.txt")


def _password() -> str:
    env = (os.environ.get("YOKUMAKUN_SSH_PASS") or os.environ.get("YOKUU_SSH_PASS") or "").strip()
    if env:
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


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 180) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST", "192.168.128.178")
    user = os.environ.get("YOKUMAKUN_SSH_USER", "tn")
    pw = _password()
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg, flush=True)

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
        sftp = client.open_sftp()
        remote_tmp = "/tmp/race_day_evening_functional_test"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        for name in (
            "race_day_evening_functional_test.py",
            "install_crontab.sh",
            "bootstrap_on_server.sh",
            "crontab.example",
        ):
            local = LOCAL_DIR / name
            if local.is_file():
                sftp.put(str(local), f"{remote_tmp}/{name}")
                log(f"uploaded {name}")
        sftp.close()

        dest = f"{REMOTE_ROOT}/server_deployment"
        cmd = " && ".join(
            [
                f"mkdir -p {shlex.quote(dest)} {shlex.quote(REMOTE_ROOT + '/logs')}",
                f"cp -f {remote_tmp}/race_day_evening_functional_test.py "
                f"{dest}/race_day_evening_functional_test.py",
                f"chmod +x {dest}/race_day_evening_functional_test.py",
                f"bash {remote_tmp}/install_crontab.sh {shlex.quote(REMOTE_ROOT)} "
                f"{dest}/race_day_evening_functional_test.py",
                f"export YOKUMAKUN_ROOT={shlex.quote(REMOTE_ROOT)}",
                f"{REMOTE_ROOT}/.venv/bin/python -m py_compile "
                f"{dest}/race_day_evening_functional_test.py",
                f"{REMOTE_ROOT}/.venv/bin/python {dest}/race_day_evening_functional_test.py "
                f"--budget-sec=120",
            ]
        )
        log("remote install + dry-run …")
        rc, out = _run(client, cmd, timeout=240)
        log(out[-4000:] if out else "(no output)")
        log(f"remote_rc={rc}")
        client.close()
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0 if rc == 0 else 1
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

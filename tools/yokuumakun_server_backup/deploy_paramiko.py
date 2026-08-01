#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows LAN から自宅サーバーへ接続し、/opt/yokuumakun_auto-x を週次バックアップと同じ場所へ保存する。"""

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
RESULT_FILE = Path(__file__).with_name("_deploy_server_backup_out.txt")
REMOTE_SCRIPT = "backup_auto_x_on_server.sh"


def _password() -> str:
    env = (os.environ.get("YOKUMAKUN_SSH_PASS") or os.environ.get("YOKUU_SSH_PASS") or "").strip()
    if env:
        return env
    for cand in (
        os.environ.get("YOKUMAKUN_SSH_CREDS", ""),
        r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt",
        r"C:\Users\tn\Desktop\ローカルサーバーIP.txt",
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


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 3600) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST") or os.environ.get("YOKUU_SSH_HOST") or "192.168.128.178"
    user = os.environ.get("YOKUMAKUN_SSH_USER") or os.environ.get("YOKUU_SSH_USER") or "tn"
    pw = _password()
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg, flush=True)

    local_script = LOCAL_DIR / REMOTE_SCRIPT
    if not local_script.is_file():
        log(f"missing {local_script}")
        RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log(f"connect {user}@{host} …")
    try:
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
    except Exception as e:
        log(f"SSH connect failed: {type(e).__name__}: {e}")
        RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
        return 1

    try:
        sftp = client.open_sftp()
        remote_tmp = "/tmp/yokuumakun_server_backup"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        remote_path = f"{remote_tmp}/{REMOTE_SCRIPT}"
        sftp.put(str(local_script), remote_path)
        sftp.close()
        log(f"uploaded {REMOTE_SCRIPT}")

        dest = (os.environ.get("YOKUMAKUN_BACKUP_DEST") or "").strip()
        include_venv = (os.environ.get("YOKUMAKUN_BACKUP_INCLUDE_VENV") or "0").strip() or "0"
        cmd = " && ".join(
            [
                f"chmod +x {shlex.quote(remote_path)}",
                f"export YOKUMAKUN_ROOT={shlex.quote(REMOTE_ROOT)}",
                f"export YOKUMAKUN_SUDO_PASS={shlex.quote(pw)}",
                f"export YOKUMAKUN_SSH_PASS={shlex.quote(pw)}",
                f"export YOKUMAKUN_BACKUP_INCLUDE_VENV={shlex.quote(include_venv)}",
                (
                    f"export YOKUMAKUN_BACKUP_DEST={shlex.quote(dest)}"
                    if dest
                    else "true"
                ),
                f"bash {shlex.quote(remote_path)}",
            ]
        )
        log("run backup on server …")
        rc, out = _run(client, cmd, timeout=3600)
        log(out[-8000:] if len(out) > 8000 else out)
        log(f"exit={rc}")
        RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
        return 0 if rc == 0 else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

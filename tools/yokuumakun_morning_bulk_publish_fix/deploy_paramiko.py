#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN から paramiko で公開漏れ修正を入れ、即 publish する。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required") from None

REMOTE_ROOT = "/opt/yokuumakun_auto-x"
LOCAL_DIR = Path(__file__).resolve().parent


def _password() -> str:
    env = (os.environ.get("YOKUMAKUN_SSH_PASS") or "").strip()
    if env:
        return env
    creds = Path(
        os.environ.get(
            "YOKUMAKUN_SSH_CREDS",
            r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt",
        )
    )
    text = creds.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(?im)^pass:\s*(\S+)\s*$", text) or re.search(
        r"(?im)^password:\s*(\S+)\s*$", text
    )
    if not m:
        raise RuntimeError("password not found")
    return m.group(1).strip()


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST", "192.168.128.178")
    user = os.environ.get("YOKUMAKUN_SSH_USER", "tn")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        username=user,
        password=_password(),
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    try:
        sftp = client.open_sftp()
        remote_tmp = "/tmp/mb_publish_fix"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        for name in (
            "force_publish_public_snapshot.py",
            "patch_worker_publish_on_success.py",
            "install_publish_endpoint.py",
            "bootstrap_on_server.sh",
        ):
            sftp.put(str(LOCAL_DIR / name), f"{remote_tmp}/{name}")
        sftp.close()
        cmd = f"bash {remote_tmp}/bootstrap_on_server.sh"
        # bootstrap は GitHub から再取得するが、オフライン時はローカルファイルで:
        cmd = (
            f"python3 {remote_tmp}/patch_worker_publish_on_success.py {REMOTE_ROOT} && "
            f"python3 {remote_tmp}/install_publish_endpoint.py {REMOTE_ROOT} && "
            f"cp {remote_tmp}/force_publish_public_snapshot.py {REMOTE_ROOT}/ && "
            f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile "
            f"force_publish_public_snapshot.py morning_bulk_server_worker.py admin_panel_api.py && "
            f"cd {REMOTE_ROOT} && .venv/bin/python force_publish_public_snapshot.py && "
            f"sudo systemctl restart yokuum-admin-panel.service && sleep 1 && "
            f"curl -sS http://127.0.0.1:8791/health"
        )
        _in, out, err = client.exec_command(cmd, timeout=300)
        sys.stdout.write(out.read().decode("utf-8", "replace"))
        sys.stderr.write(err.read().decode("utf-8", "replace"))
        return out.channel.recv_exit_status()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

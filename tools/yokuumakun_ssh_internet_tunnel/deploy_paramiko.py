#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN 上から paramiko で SSH インターネット公開トンネルを入れる。"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required: pip install paramiko") from None

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
        remote_tmp = "/tmp/ssh_internet_tunnel"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        for name in (
            "ssh_tcp_tunnel.sh",
            "publish_ssh_endpoint.py",
            "yokuum-ssh-tcp-tunnel.service.example",
            "bootstrap_on_server.sh",
        ):
            sftp.put(str(LOCAL_DIR / name), f"{remote_tmp}/{name}")
        sftp.close()

        cmd = (
            f"sed -i 's/\\r$//' {remote_tmp}/*.sh && "
            f"bash {remote_tmp}/bootstrap_on_server.sh"
        )
        _in, out, err = client.exec_command(cmd, timeout=300)
        sys.stdout.write(out.read().decode("utf-8", "replace"))
        sys.stderr.write(err.read().decode("utf-8", "replace"))
        rc = out.channel.recv_exit_status()
        if rc != 0:
            return rc

        # verify public endpoint
        for _ in range(15):
            _in, out, err = client.exec_command(
                "curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json",
                timeout=30,
            )
            body = out.read().decode("utf-8", "replace")
            if '"port"' in body:
                print(body)
                return 0
            time.sleep(2)
        print("endpoint not visible yet", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

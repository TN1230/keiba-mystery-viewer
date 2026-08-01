#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN 上から paramiko で SSH インターネット公開トンネルを入れる。

以前成功していた deploy_*_paramiko.py と同じく echo pass | sudo -S を使う。
"""

from __future__ import annotations

import os
import re
import shlex
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
    for cand in (
        os.environ.get("YOKUMAKUN_SSH_CREDS", ""),
        r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt",
        r"C:\Users\user\Desktop\ローカルサーバーIP.txt",
    ):
        if not cand:
            continue
        creds = Path(cand)
        if not creds.is_file():
            continue
        text = creds.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?im)^pass:\s*(\S+)\s*$", text) or re.search(
            r"(?im)^password:\s*(\S+)\s*$", text
        )
        if m:
            return m.group(1).strip()
    raise RuntimeError("password not found")


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 300) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def _sudo(pw: str, cmd: str) -> str:
    return f"echo {shlex.quote(pw)} | sudo -S -p '' {cmd}"


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST", "192.168.128.178")
    user = os.environ.get("YOKUMAKUN_SSH_USER", "tn")
    pw = _password()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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

        # curl|bash ではなく直接インストール（sudo -S）
        cmd = " && ".join(
            [
                f"mkdir -p {REMOTE_ROOT}/server_deployment {REMOTE_ROOT}/logs {REMOTE_ROOT}/.local/bin",
                f"sed -i 's/\\r$//' {remote_tmp}/ssh_tcp_tunnel.sh {remote_tmp}/bootstrap_on_server.sh",
                f"install -m 0755 {remote_tmp}/ssh_tcp_tunnel.sh {REMOTE_ROOT}/server_deployment/ssh_tcp_tunnel.sh",
                f"install -m 0644 {remote_tmp}/publish_ssh_endpoint.py {REMOTE_ROOT}/publish_ssh_endpoint.py",
                f"install -m 0644 {remote_tmp}/yokuum-ssh-tcp-tunnel.service.example "
                f"{REMOTE_ROOT}/server_deployment/yokuum-ssh-tcp-tunnel.service.example",
                _sudo(
                    pw,
                    f"cp {REMOTE_ROOT}/server_deployment/yokuum-ssh-tcp-tunnel.service.example "
                    f"/etc/systemd/system/yokuum-ssh-tcp-tunnel.service",
                ),
                _sudo(pw, "systemctl daemon-reload"),
                _sudo(pw, "systemctl enable yokuum-ssh-tcp-tunnel.service"),
                _sudo(pw, "systemctl restart yokuum-ssh-tcp-tunnel.service"),
                "sleep 2",
                "systemctl is-active yokuum-ssh-tcp-tunnel.service",
            ]
        )
        rc, out = _run(client, cmd, timeout=300)
        sys.stdout.write(out.replace(pw, "***"))
        if rc != 0:
            _, j = _run(
                client,
                _sudo(pw, "journalctl -u yokuum-ssh-tcp-tunnel.service -n 80 --no-pager"),
                timeout=60,
            )
            sys.stderr.write(j.replace(pw, "***"))
            return rc

        public_url = (
            "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
            "public-viewer/ssh_endpoint.json"
        )
        for _ in range(30):
            _, body = _run(client, f"curl -fsSL {shlex.quote(public_url)} || true", timeout=30)
            local = ""
            _, local = _run(
                client,
                f"cat {REMOTE_ROOT}/logs/ssh_endpoint.local.json 2>/dev/null || true",
                timeout=30,
            )
            print(body or local)
            if '"port"' in (body + local):
                return 0
            time.sleep(2)
        _, j = _run(
            client,
            _sudo(pw, "journalctl -u yokuum-ssh-tcp-tunnel.service -n 80 --no-pager"),
            timeout=60,
        )
        print(j.replace(pw, "***"), file=sys.stderr)
        print("endpoint not visible yet", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

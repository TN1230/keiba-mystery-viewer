#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN Windows から paramiko で未適用パッチを一括投入する（以前成功した方式）。

適用内容:
  1) SSH internet tunnel (bore) + ssh_endpoint.json 公開
  2) morning-bulk 成功時 public snapshot 公開漏れ修正 + 即 force publish
  3) morning-bulk TEST_ALWAYS webhook フィルタ

使い方 (Windows / LAN):
  python deploy_paramiko.py
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
HERE = Path(__file__).resolve().parent
SSH_TUNNEL_DIR = HERE.parent / "yokuumakun_ssh_internet_tunnel"
PUBLISH_BRANCH = "cursor/morning-bulk-publish-fix-19c2"
FILTER_BRANCH = "cursor/morning-bulk-test-webhook-filter-19c2"


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
    raise RuntimeError("SSH password not found (YOKUMAKUN_SSH_PASS or ローカルサーバーIP.txt)")


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 300) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out


def _sudo(pw: str, cmd: str) -> str:
    # 以前成功していた方式: echo pass | sudo -S
    return f"echo {shlex.quote(pw)} | sudo -S -p '' {cmd}"


def _ensure_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts: list[str] = []
    p = remote_dir
    while p and p != "/":
        parts.append(p)
        p = os.path.dirname(p)
    for d in reversed(parts):
        try:
            sftp.stat(d)
        except OSError:
            sftp.mkdir(d)


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST", "192.168.128.178")
    user = os.environ.get("YOKUMAKUN_SSH_USER", "tn")
    pw = _password()
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg, flush=True)

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
    try:
        sftp = client.open_sftp()
        remote_tmp = "/tmp/yokuumakun_lan_apply_pending"
        _ensure_dir(sftp, remote_tmp)

        # --- 1) SSH tunnel files (local copy; bootstrap also pulls GitHub) ---
        if SSH_TUNNEL_DIR.is_dir():
            for name in (
                "ssh_tcp_tunnel.sh",
                "publish_ssh_endpoint.py",
                "yokuum-ssh-tcp-tunnel.service.example",
                "bootstrap_on_server.sh",
            ):
                local = SSH_TUNNEL_DIR / name
                if local.is_file():
                    sftp.put(str(local), f"{remote_tmp}/{name}")
                    log(f"uploaded tunnel/{name}")

        sftp.close()

        # sudo がパスワード付きで動くか確認
        rc, out = _run(client, _sudo(pw, "true") + " && echo SUDO_OK", timeout=60)
        log(f"sudo check rc={rc} {out.strip()}")
        if "SUDO_OK" not in out:
            log("ERROR: sudo -S failed; abort")
            return 1

        # --- publish fix + webhook filter via curl bootstrap (GitHub raw) ---
        cmds = [
            (
                "publish_fix",
                "curl -fsSL "
                f"https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/{PUBLISH_BRANCH}/"
                "tools/yokuumakun_morning_bulk_publish_fix/bootstrap_on_server.sh | bash",
            ),
            (
                "webhook_filter",
                "curl -fsSL "
                f"https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/{FILTER_BRANCH}/"
                "tools/yokuumakun_morning_bulk_test_webhook_filter/bootstrap_on_server.sh | bash",
            ),
        ]
        for name, cmd in cmds:
            # bootstrap 内の sudo 向けに askpass 風へ
            wrapped = (
                f"export YOKUMAKUN_ROOT={shlex.quote(REMOTE_ROOT)}; "
                f"export SUDO_ASKPASS=/bin/false; "
                # sudo をラップ: 非対話で -S を使うヘルパを PATH 先頭へ
                f"mkdir -p /tmp/yk_sudo_wrap && "
                f"printf '%s\\n' '#!/bin/bash' "
                f"'echo {shlex.quote(pw)} | /usr/bin/sudo -S -p \"\" \"$@\"' "
                f"> /tmp/yk_sudo_wrap/sudo && chmod 755 /tmp/yk_sudo_wrap/sudo && "
                f"export PATH=/tmp/yk_sudo_wrap:$PATH && {cmd}"
            )
            log(f"=== run {name} ===")
            rc, out = _run(client, wrapped, timeout=420)
            # パスワードをログから除去
            safe = out.replace(pw, "***")
            log(safe[-4000:] if len(safe) > 4000 else safe)
            log(f"=== {name} rc={rc} ===")

        # --- SSH tunnel: ローカルアップロード版を sudo -S で直接入れる（curl|bash の sudo 失敗を回避） ---
        log("=== install ssh tunnel (direct, sudo -S) ===")
        tunnel_cmd = " && ".join(
            [
                f"mkdir -p {REMOTE_ROOT}/server_deployment {REMOTE_ROOT}/logs {REMOTE_ROOT}/.local/bin",
                f"sed -i 's/\\r$//' {remote_tmp}/ssh_tcp_tunnel.sh",
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
                "systemctl is-active yokuum-ssh-tcp-tunnel.service || true",
                _sudo(pw, "systemctl --no-pager --full status yokuum-ssh-tcp-tunnel.service | head -25"),
            ]
        )
        rc, out = _run(client, tunnel_cmd, timeout=300)
        log(out.replace(pw, "***"))
        log(f"tunnel install rc={rc}")

        # wait for endpoint
        public_url = (
            "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
            "public-viewer/ssh_endpoint.json"
        )
        endpoint_ok = False
        for i in range(30):
            rc, out = _run(
                client,
                f"test -f {REMOTE_ROOT}/logs/ssh_endpoint.local.json && "
                f"cat {REMOTE_ROOT}/logs/ssh_endpoint.local.json; "
                f"curl -fsSL {shlex.quote(public_url)} 2>/dev/null || true",
                timeout=60,
            )
            log(f"endpoint try {i+1}: {out.strip()[:500]}")
            if '"port"' in out:
                endpoint_ok = True
                break
            # journal hint
            if i in (5, 15, 25):
                _, jout = _run(
                    client,
                    _sudo(pw, "journalctl -u yokuum-ssh-tcp-tunnel.service -n 40 --no-pager"),
                    timeout=60,
                )
                log(jout.replace(pw, "***")[-2000:])
            time.sleep(2)

        # snapshot verify
        rc, out = _run(
            client,
            "curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
            "public-viewer/snapshots/latest.json | head -c 400",
            timeout=60,
        )
        log(f"snapshot: {out}")

        if endpoint_ok:
            log("RESULT: SUCCESS (ssh endpoint published)")
            return 0
        log("RESULT: PARTIAL (patches may be applied; ssh_endpoint not public yet — see journal above)")
        return 2
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

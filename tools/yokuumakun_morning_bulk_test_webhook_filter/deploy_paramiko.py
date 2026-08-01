#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN 上の Windows などから paramiko でサーバへフィルタを入れる。

環境変数:
  YOKUMAKUN_SSH_HOST   既定 192.168.128.178
  YOKUMAKUN_SSH_USER   既定 tn
  YOKUMAKUN_SSH_PASS   必須（または CREDS ファイル）
  YOKUMAKUN_SSH_CREDS  既定 C:\\Users\\mocco\\Desktop\\ローカルサーバーIP.txt
"""

from __future__ import annotations

import os
import re
import sys
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
    )
    try:
        sftp = client.open_sftp()
        remote_tmp = "/tmp/mb_tw_filter"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        for name in (
            "morning_bulk_test_webhook_filter.py",
            "install_into_ops_discord_notify.py",
        ):
            sftp.put(str(LOCAL_DIR / name), f"{remote_tmp}/{name}")
        sftp.close()

        cmd = (
            f"python3 {remote_tmp}/install_into_ops_discord_notify.py {REMOTE_ROOT} && "
            f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile "
            f"morning_bulk_test_webhook_filter.py ops_discord_notify.py && "
            f"cd {REMOTE_ROOT} && .venv/bin/python -c \""
            f"from morning_bulk_test_webhook_filter import allow_morning_bulk_test_always as a; "
            f"assert a('morning_bulk_worker_start','ok') and not a('morning_bulk_cache_flush','ok'); "
            f"import ops_discord_notify as o; "
            f"assert getattr(o.notify_action,'morning_bulk_test_webhook_filter',False); "
            f"print('OK', o.__file__)\""
        )
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        print(out)
        if err:
            print(err, file=sys.stderr)
        return rc
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

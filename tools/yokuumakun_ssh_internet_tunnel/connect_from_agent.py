#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開済み ssh_endpoint.json を読み、インターネット経由で SSH する。

例:
  YOKUMAKUN_SSH_PASS=... python connect_from_agent.py -- hostname
  YOKUMAKUN_SSH_PASS=... python connect_from_agent.py -- 'cd /opt/yokuumakun_auto-x && .venv/bin/python force_publish_public_snapshot.py'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required") from None

DEFAULT_ENDPOINT = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/ssh_endpoint.json"
)


def fetch_endpoint(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT)
    ap.add_argument("--password-env", default="YOKUMAKUN_SSH_PASS")
    ap.add_argument("remote_cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)

    cmd_parts = list(args.remote_cmd)
    if cmd_parts and cmd_parts[0] == "--":
        cmd_parts = cmd_parts[1:]
    if not cmd_parts:
        print("usage: connect_from_agent.py -- <remote command>", file=sys.stderr)
        return 2

    ep = fetch_endpoint(args.endpoint_url)
    host = ep["host"]
    port = int(ep["port"])
    user = ep.get("user") or "tn"
    password = (os.environ.get(args.password_env) or "").strip()
    if not password:
        print(f"ERROR: set {args.password_env}", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=port,
        username=user,
        password=password,
        timeout=45,
        allow_agent=False,
        look_for_keys=False,
        banner_timeout=45,
    )
    try:
        remote = " ".join(cmd_parts)
        print(f"SSH {user}@{host}:{port} :: {remote}", file=sys.stderr)
        _in, out, err = client.exec_command(remote, timeout=600)
        sys.stdout.write(out.read().decode("utf-8", "replace"))
        sys.stderr.write(err.read().decode("utf-8", "replace"))
        return out.channel.recv_exit_status()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

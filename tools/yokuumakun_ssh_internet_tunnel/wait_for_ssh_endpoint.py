#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ssh_endpoint.json が公開されるまで待ち、任意で接続確認する。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/ssh_endpoint.json"
)


def fetch(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url + ("&" if "?" in url else "?") + f"t={int(time.time())}", timeout=20) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, dict) and data.get("host") and data.get("port"):
            return data
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    return None


def try_connect(ep: dict, password: str) -> int:
    try:
        import paramiko
    except ImportError:
        print("WARN: paramiko not installed; skip connect check", file=sys.stderr)
        return 0
    host = str(ep["host"])
    port = int(ep["port"])
    user = str(ep.get("user") or "tn")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
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
        _in, out, err = client.exec_command("hostname && date -Iseconds", timeout=60)
        sys.stdout.write(out.read().decode("utf-8", "replace"))
        sys.stderr.write(err.read().decode("utf-8", "replace"))
        return out.channel.recv_exit_status()
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--timeout-sec", type=int, default=900)
    ap.add_argument("--interval-sec", type=float, default=10.0)
    ap.add_argument("--connect", action="store_true", help="公開後に SSH 接続確認")
    ap.add_argument("--password-env", default="YOKUMAKUN_SSH_PASS")
    args = ap.parse_args(argv)

    deadline = time.time() + max(1, args.timeout_sec)
    print(f"waiting for {args.url}", flush=True)
    while time.time() < deadline:
        ep = fetch(args.url)
        if ep:
            print(json.dumps(ep, ensure_ascii=False, indent=2), flush=True)
            if args.connect:
                pw = (os.environ.get(args.password_env) or "").strip()
                if not pw:
                    print(f"ERROR: set {args.password_env} for --connect", file=sys.stderr)
                    return 2
                return try_connect(ep, pw)
            return 0
        time.sleep(max(1.0, args.interval_sec))
    print("ERROR: timed out waiting for ssh_endpoint.json", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

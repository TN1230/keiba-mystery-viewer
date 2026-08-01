#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSH 到達情報を Supabase Storage (public-viewer/ssh_endpoint.json) に書き出す。

使い方:
  python publish_ssh_endpoint.py --host bore.pub --port 12345
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore

import urllib.error
import urllib.request

_JST = ZoneInfo("Asia/Tokyo")


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    # tools/.../publish_ssh_endpoint.py → server root when copied to ROOT/
    here = Path(__file__).resolve().parent
    if (here / ".env").is_file() or (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def _load_env() -> None:
    if load_dotenv is None:
        return
    root = _root()
    for p in (root / ".env", root / "server_deployment" / "hwm_runtime.env"):
        if p.is_file():
            load_dotenv(p, override=False)


def publish(payload: dict) -> str:
    _load_env()
    supabase = (os.environ.get("SUPABASE_URL") or "").strip().strip('"').rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    ).strip().strip('"')
    bucket = (os.environ.get("SUPABASE_PUBLIC_VIEWER_BUCKET") or "public-viewer").strip()
    if not supabase or not key:
        raise RuntimeError("SUPABASE_URL / SERVICE_ROLE_KEY missing")

    object_path = "ssh_endpoint.json"
    upload_url = f"{supabase}/storage/v1/object/{bucket}/{object_path}?upsert=true"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        upload_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
            "x-upsert": "true",
            "User-Agent": "yokuumakun-ssh-endpoint/1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            _ = resp.read()
            if resp.status not in (200, 201):
                raise RuntimeError(f"upload HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"upload HTTP {e.code}: {e.read()[:400]!r}") from e

    return f"{supabase}/storage/v1/object/public/{bucket}/{object_path}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", required=True, type=int)
    ap.add_argument("--user", default="tn")
    ap.add_argument("--provider", default="bore")
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv)

    payload = {
        "host": args.host.strip(),
        "port": int(args.port),
        "user": args.user.strip() or "tn",
        "provider": args.provider.strip() or "bore",
        "ssh_command": f"ssh -p {int(args.port)} {args.user}@{args.host}",
        "updated_at": datetime.now(_JST).isoformat(timespec="seconds"),
        "note": args.note,
    }
    try:
        public = publish(payload)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"OK {public}")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bootstrap 結果を public-viewer/ops/lan_site_publish_last.json に書き出す。"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
        rt = root / "server_deployment" / "hwm_runtime.env"
        if rt.is_file():
            load_dotenv(rt, override=False)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/opt/yokuumakun_auto-x")
    ap.add_argument("--log", default="/tmp/lan_site_publish.log")
    ap.add_argument("--rc", type=int, default=1)
    args = ap.parse_args()
    root = Path(args.root)
    _load_env(root)

    log_tail = ""
    lp = Path(args.log)
    if lp.is_file():
        try:
            log_tail = lp.read_text(encoding="utf-8", errors="replace")[-12000:]
        except Exception as e:
            log_tail = f"<read_error {e}>"

    # local diagnostics
    logs = root / "logs"
    pkls = []
    flags = []
    if logs.is_dir():
        pkls = sorted([p.name for p in logs.glob("morning_bulk_races_*.pkl")])[-20:]
        flags = sorted([p.name for p in logs.glob("morning_bulk_done_*.flag")])[-20:]

    payload = {
        "updated_at": datetime.now(_JST).isoformat(timespec="seconds"),
        "rc": args.rc,
        "root": str(root),
        "pkls": pkls,
        "done_flags": flags,
        "log_tail": log_tail,
        "hostname": os.uname().nodename if hasattr(os, "uname") else "",
    }

    # 1) サーバー側 export ヘルパ経由（.env の読み方が揃っている）
    try:
        import sys

        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        url, err = upload_json_object("ops/lan_site_publish_last.json", payload)
        if not err:
            print(f"OK uploaded status via export_upload")
            print(url)
            return 0
        print(f"WARN: export_upload failed: {err}", flush=True)
    except Exception as e:
        print(f"WARN: export_upload exc: {type(e).__name__}: {e}", flush=True)

    supabase = (os.environ.get("SUPABASE_URL") or "").strip().strip('"').rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or ""
    ).strip().strip('"')
    bucket = (os.environ.get("SUPABASE_PUBLIC_VIEWER_BUCKET") or "public-viewer").strip()
    if not supabase or not key:
        print("WARN: no supabase creds for status upload", flush=True)
        return 0

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    object_path = "ops/lan_site_publish_last.json"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "x-upsert": "true",
        "User-Agent": "yokuumakun-lan-site-publish/1",
    }
    last_err = None
    for method, url in (
        ("POST", f"{supabase}/storage/v1/object/{bucket}/{object_path}?upsert=true"),
        ("PUT", f"{supabase}/storage/v1/object/{bucket}/{object_path}"),
    ):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                _ = resp.read()
            print(f"OK uploaded status via {method}")
            print(
                f"{supabase}/storage/v1/object/public/{bucket}/{object_path}"
            )
            return 0
        except urllib.error.HTTPError as e:
            last_err = f"{method} {e.code}: {e.read()[:300]!r}"
        except Exception as e:
            last_err = f"{method} {type(e).__name__}: {e}"
    print(f"WARN: status upload failed: {last_err}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

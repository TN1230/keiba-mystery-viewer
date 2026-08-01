#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin_api.json に tenkai_sim_url_template を載せる（既存 base_url を維持）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore

_JST = ZoneInfo("Asia/Tokyo")
PUBLIC_DISCOVERY = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/admin_api.json"
)


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
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


def _fetch_current() -> dict[str, Any]:
    try:
        with urllib.request.urlopen(PUBLIC_DISCOVERY, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def publish(base_url: str, template: str) -> str:
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

    cur = _fetch_current()
    base = (base_url or cur.get("base_url") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        raise RuntimeError(f"invalid base_url: {base!r}")

    tpl = (template or "").strip() or f"{base}/tenkai?race_id={{race_id}}&place={{place}}&R={{R}}&schedule_date={{schedule_date}}"
    payload = {
        "base_url": base,
        "updated_at": datetime.now(_JST).isoformat(timespec="seconds"),
        "tenkai_sim_url_template": tpl,
    }
    # 既存の任意キーは維持
    for k, v in cur.items():
        if k not in payload:
            payload[k] = v

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "x-upsert": "true",
        "User-Agent": "yokuumakun-tenkai-discovery/1",
    }
    object_path = "admin_api.json"
    last_err: Optional[Exception] = None
    for method, url in (
        ("POST", f"{supabase}/storage/v1/object/{bucket}/{object_path}?upsert=true"),
        ("PUT", f"{supabase}/storage/v1/object/{bucket}/{object_path}"),
    ):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                _ = resp.read()
                if resp.status not in (200, 201):
                    last_err = RuntimeError(f"upload HTTP {resp.status}")
                    continue
            last_err = None
            break
        except urllib.error.HTTPError as e:
            last_err = RuntimeError(f"upload {method} HTTP {e.code}: {e.read()[:400]!r}")
            continue
    if last_err is not None:
        raise last_err
    public = f"{supabase}/storage/v1/object/public/{bucket}/{object_path}"
    print(f"OK {public}")
    print(json.dumps(payload, ensure_ascii=False))
    return public


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="")
    ap.add_argument("--template", default="")
    args = ap.parse_args(argv)
    try:
        publish(args.base_url, args.template)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""閲覧サイト snapshots/latest.json を EOD クリア（公開終了表示）にする。

使い方（サーバー）:
  cd /opt/yokuumakun_auto-x && .venv/bin/python clear_latest_public_snapshot.py
  .venv/bin/python clear_latest_public_snapshot.py --day 2026-08-01
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
PUBLIC_LATEST = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/snapshots/latest.json"
)


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    for cand in (here, Path("/opt/yokuumakun_auto-x")):
        if (cand / "hwm.py").is_file() or (cand / ".env").is_file():
            return cand.resolve()
    return Path("/opt/yokuumakun_auto-x")


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
        rt = root / "server_deployment" / "hwm_runtime.env"
        if rt.is_file():
            load_dotenv(rt, override=False)
    except Exception:
        pass


def _today() -> str:
    return datetime.now(_JST).strftime("%Y-%m-%d")


def _fetch_latest() -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(PUBLIC_LATEST, timeout=30) as resp:
            snap = json.loads(resp.read().decode())
        return snap if isinstance(snap, dict) else None
    except Exception:
        return None


def build_cleared_snapshot(day: str, *, prev: dict[str, Any] | None = None) -> dict[str, Any]:
    now = datetime.now(_JST).strftime("%Y-%m-%dT%H:%M:%S")
    mode = "15"
    pre_line = "・発走15分前前後（全レース）"
    timing = (
        "【主な更新タイミング】\n"
        "・開催日早朝6時頃（全レース一斉）\n"
        "・発走1時間前頃（重賞のみ）\n"
        f"{pre_line}\n"
        "※更新されない場合は通信障害など運用上のトラブルが発生しております。ご容赦ください"
    )
    if prev:
        mode = str(prev.get("pre_race_trigger_mode") or mode)
        pre_line = str(prev.get("update_timing_pre_race_line") or pre_line)
        timing = str(prev.get("update_timing_text") or timing)
    return {
        "schema_version": 3,
        "updated_at": now,
        "schedule_date": day,
        "top5": [],
        "venues": [],
        "race_count": 0,
        "venue_count": 0,
        "cleared": True,
        "pre_race_trigger_mode": mode,
        "update_timing_pre_race_line": pre_line,
        "update_timing_text": timing,
    }


def _upload_via_export(root: Path, snap: dict[str, Any]) -> tuple[str | None, str]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        url, err = upload_json_object("snapshots/latest.json", snap)
        if err:
            return None, str(err)
        return str(url or ""), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _upload_via_rest(snap: dict[str, Any]) -> tuple[str | None, str]:
    supabase = (os.environ.get("SUPABASE_URL") or "").strip().strip('"').rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or ""
    ).strip().strip('"')
    bucket = (os.environ.get("SUPABASE_PUBLIC_VIEWER_BUCKET") or "public-viewer").strip()
    if not supabase or not key:
        return None, "supabase_creds_missing"
    body = json.dumps(snap, ensure_ascii=False).encode("utf-8")
    object_path = "snapshots/latest.json"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "x-upsert": "true",
        "User-Agent": "yokuumakun-clear-latest/1",
    }
    last_err = ""
    for method, url in (
        ("POST", f"{supabase}/storage/v1/object/{bucket}/{object_path}?upsert=true"),
        ("PUT", f"{supabase}/storage/v1/object/{bucket}/{object_path}"),
    ):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                _ = resp.read()
            return f"{supabase}/storage/v1/object/public/{bucket}/{object_path}", ""
        except urllib.error.HTTPError as e:
            last_err = f"{method} {e.code}: {e.read()[:200]!r}"
        except Exception as e:
            last_err = f"{method} {type(e).__name__}: {e}"
    return None, last_err or "upload_failed"


def run_clear(*, day: str | None = None, root: Path | None = None) -> dict[str, Any]:
    root = root or _root()
    os.chdir(root)
    _load_env(root)
    day = day or _today()
    prev = _fetch_latest()
    snap = build_cleared_snapshot(day, prev=prev)
    url, err = _upload_via_export(root, snap)
    via = "export_upload"
    if err:
        url2, err2 = _upload_via_rest(snap)
        if err2:
            return {
                "ok": False,
                "day": day,
                "error": f"export={err}; rest={err2}",
                "snapshot": snap,
            }
        url, err, via = url2, "", "rest"
    # verify
    after = _fetch_latest() or {}
    ok = bool(after.get("cleared") is True) and int(after.get("race_count") or 0) == 0
    return {
        "ok": ok,
        "day": day,
        "via": via,
        "url": url,
        "cleared": after.get("cleared"),
        "race_count": after.get("race_count"),
        "updated_at": after.get("updated_at"),
        "schedule_date": after.get("schedule_date"),
    }


def main(argv: list[str]) -> int:
    day = None
    for a in argv[1:]:
        if a.startswith("--day="):
            day = a.split("=", 1)[1].strip()
    out = run_clear(day=day)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

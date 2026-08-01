#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""朝一斉完了後に latest.json が空/前日のままなら強制 publish する常駐向けスクリプト。

systemd timer または cron から数分おきに呼ぶ。すでに当日分が公開済みなら何もしない。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
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
    if (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def _today() -> str:
    return datetime.now(_JST).strftime("%Y-%m-%d")


def _done_flag_exists(root: Path, day: str) -> bool:
    logs = root / "logs"
    if not logs.is_dir():
        return False
    for p in logs.glob(f"morning_bulk_done_*{day}.flag"):
        if p.is_file():
            return True
    plain = logs / f"morning_bulk_done_{day}.flag"
    return plain.is_file()


def _cache_exists(root: Path, day: str) -> bool:
    logs = root / "logs"
    ymd = day.replace("-", "")
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        if (logs / name).is_file():
            return True
    return False


def _public_needs_publish(day: str) -> bool:
    try:
        with urllib.request.urlopen(PUBLIC_LATEST, timeout=30) as resp:
            snap = json.loads(resp.read().decode())
    except Exception:
        return True
    if snap.get("cleared") is True:
        return True
    if str(snap.get("schedule_date") or "") != day:
        return True
    if int(snap.get("race_count") or 0) <= 0:
        return True
    return False


def main() -> int:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    day = _today()
    out: dict = {"day": day, "action": "noop"}

    if not _done_flag_exists(root, day) and not _cache_exists(root, day):
        out["reason"] = "no_morning_bulk_done_or_cache"
        print(json.dumps(out, ensure_ascii=False))
        return 0

    if not _public_needs_publish(day):
        out["reason"] = "already_published"
        print(json.dumps(out, ensure_ascii=False))
        return 0

    from force_publish_public_snapshot import run_publish

    result = run_publish(force=True)
    out["action"] = "force_publish"
    out["result"] = result
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

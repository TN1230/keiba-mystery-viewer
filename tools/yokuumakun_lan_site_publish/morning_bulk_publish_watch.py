#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""閲覧サイト latest.json の公開遅れを拾って強制 publish する常駐向けスクリプト。

用途:
1. 朝一斉完了なのに latest が空/前日 → publish
2. 直前予想成功でキャッシュの predicted_at が公開より新しい → publish
   （本日: 札幌4〜9Rは公開更新されたが、その後キャッシュ更新がサイトへ乗らない）

systemd timer または cron から数分おきに呼ぶ。
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
PUBLIC_LATEST = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/snapshots/latest.json"
)
# 直前成功は発走約15分前。公開がそれ以上遅れたら保険 publish。
_STALE_AFTER = timedelta(minutes=8)
_PRE_RACE_LOOKAHEAD = timedelta(minutes=25)
_PRE_RACE_LOOKBACK = timedelta(minutes=5)


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


def _cache_paths(root: Path, day: str) -> list[Path]:
    logs = root / "logs"
    ymd = day.replace("-", "")
    out: list[Path] = []
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        fp = logs / name
        if fp.is_file():
            out.append(fp)
    return out


def _cache_exists(root: Path, day: str) -> bool:
    return bool(_cache_paths(root, day))


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("T", " ").replace("Z", "")
    if "+" in s[10:]:
        s = s.split("+", 1)[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=_JST)
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_JST)
        return dt.astimezone(_JST)
    except Exception:
        return None


def _iter_public_races(snap: dict[str, Any]) -> list[dict[str, Any]]:
    races: list[dict[str, Any]] = []
    for v in snap.get("venues") or []:
        if isinstance(v, dict):
            for r in v.get("races") or []:
                if isinstance(r, dict):
                    races.append(r)
    return races


def _max_predicted_at_from_public(snap: dict[str, Any]) -> datetime | None:
    best: datetime | None = None
    for r in _iter_public_races(snap):
        dt = _parse_dt(r.get("predicted_at"))
        if dt and (best is None or dt > best):
            best = dt
    return best


def _max_predicted_at_from_cache(root: Path, day: str) -> datetime | None:
    best: datetime | None = None
    for fp in _cache_paths(root, day):
        try:
            with fp.open("rb") as f:
                races = pickle.load(f)
        except Exception:
            continue
        if not isinstance(races, dict):
            continue
        for rinfo in races.values():
            if not isinstance(rinfo, dict):
                continue
            dt = _parse_dt(rinfo.get("predicted_at"))
            if dt and (best is None or dt > best):
                best = dt
    return best


def _fetch_public() -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(PUBLIC_LATEST, timeout=30) as resp:
            snap = json.loads(resp.read().decode())
        return snap if isinstance(snap, dict) else None
    except Exception:
        return None


def _public_empty_or_wrong_day(snap: dict[str, Any] | None, day: str) -> bool:
    if snap is None:
        return True
    if snap.get("cleared") is True:
        return True
    if str(snap.get("schedule_date") or "") != day:
        return True
    if int(snap.get("race_count") or 0) <= 0:
        return True
    return False


def _public_stale_vs_cache(
    snap: dict[str, Any], root: Path, day: str
) -> tuple[bool, str]:
    """キャッシュの predicted_at が公開より新しければ再 publish。"""
    cache_max = _max_predicted_at_from_cache(root, day)
    if cache_max is None:
        return False, "no_cache_predicted_at"
    pub_max = _max_predicted_at_from_public(snap)
    if pub_max is None or cache_max > pub_max + timedelta(seconds=30):
        return True, f"cache_pred={cache_max.isoformat()} public_pred={pub_max}"
    return False, "cache_not_newer"


def _public_stale_during_prerace_window(snap: dict[str, Any]) -> tuple[bool, str]:
    """本日成功パターン: 発走15分前更新。公開 updated_at が古い＆窓内レースが朝のままなら再 publish。"""
    now = datetime.now(_JST)
    updated = _parse_dt(snap.get("updated_at"))
    if updated is None:
        return True, "missing_updated_at"
    if now - updated < _STALE_AFTER:
        return False, "updated_recently"

    window_start = now - _PRE_RACE_LOOKBACK
    window_end = now + _PRE_RACE_LOOKAHEAD
    stale_in_window = 0
    for r in _iter_public_races(snap):
        start_s = str(r.get("start_time") or "").strip()
        if not start_s or ":" not in start_s:
            continue
        try:
            hh, mm = start_s.split(":")[:2]
            start_dt = now.replace(
                hour=int(hh), minute=int(mm), second=0, microsecond=0
            )
        except Exception:
            continue
        if not (window_start <= start_dt <= window_end):
            continue
        pred = _parse_dt(r.get("predicted_at"))
        # 発走20分以上前の predicted_at のまま = 直前成功が未反映
        if pred is None or (start_dt - pred) > timedelta(minutes=20):
            stale_in_window += 1
    if stale_in_window > 0:
        return True, f"stale_prerace_races={stale_in_window} updated_at={updated.isoformat()}"
    return False, "no_stale_prerace_window"


def decide_publish(root: Path, day: str, snap: dict[str, Any] | None) -> dict[str, Any]:
    """テスト用: publish 要否を判定する。"""
    out: dict[str, Any] = {"day": day, "action": "noop"}
    if not _done_flag_exists(root, day) and not _cache_exists(root, day):
        out["reason"] = "no_morning_bulk_done_or_cache"
        return out

    if _public_empty_or_wrong_day(snap, day):
        out["action"] = "force_publish"
        out["reason"] = "empty_or_wrong_day"
        return out

    assert snap is not None
    newer, why = _public_stale_vs_cache(snap, root, day)
    if newer:
        out["action"] = "force_publish"
        out["reason"] = "cache_newer_than_public"
        out["detail"] = why
        return out

    stale, why2 = _public_stale_during_prerace_window(snap)
    if stale:
        out["action"] = "force_publish"
        out["reason"] = "stale_during_prerace"
        out["detail"] = why2
        return out

    out["reason"] = "already_fresh"
    out["detail"] = why
    return out


def main() -> int:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    day = _today()
    snap = _fetch_public()
    out = decide_publish(root, day, snap)

    if out.get("action") != "force_publish":
        print(json.dumps(out, ensure_ascii=False, default=str))
        return 0

    from force_publish_public_snapshot import run_publish

    result = run_publish(force=True)
    out["result"] = result
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

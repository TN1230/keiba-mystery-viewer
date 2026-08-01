#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""朝一斉レースキャッシュから閲覧サイト latest.json を強制 publish する。

サーバー上:
  cd /opt/yokuumakun_auto-x && .venv/bin/python force_publish_public_snapshot.py
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    if (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
    except Exception:
        pass
    rt = root / "server_deployment" / "hwm_runtime.env"
    if rt.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(rt, override=False)
        except Exception:
            pass


def _try_load_pkl(fp: Path) -> dict[str, Any]:
    try:
        with fp.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict) and data:
            return data
    except Exception:
        pass
    return {}


def _day_from_name(name: str) -> str:
    # morning_bulk_races_YYYYMMDD.pkl / morning_bulk_races_YYYY-MM-DD.pkl
    stem = name.replace("morning_bulk_races_", "").replace(".pkl", "")
    if len(stem) == 8 and stem.isdigit():
        return f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}"
    return stem


def _load_races(root: Path) -> tuple[str, dict[str, Any], list[str]]:
    notes: list[str] = []
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # 1) 公式ヘルパ
    try:
        from hwm_server_standalone import (  # type: ignore
            _load_morning_bulk_races_cache,
            effective_schedule_date_iso,
        )

        day = str(effective_schedule_date_iso())
        races = _load_morning_bulk_races_cache(day) or {}
        if races:
            notes.append(f"helper_cache day={day} n={len(races)}")
            return day, races, notes
        notes.append(f"helper_cache empty day={day}")
    except Exception as e:
        notes.append(f"helper_cache err={type(e).__name__}:{e}")

    logs = root / "logs"
    today = datetime.now(_JST).strftime("%Y-%m-%d")
    candidates: list[tuple[float, str, Path]] = []

    # 2) 日付候補を広く探す
    days = [today]
    for delta in range(1, 4):
        days.append((datetime.now(_JST) - timedelta(days=delta)).strftime("%Y-%m-%d"))
        days.append((datetime.now(_JST) + timedelta(days=delta)).strftime("%Y-%m-%d"))

    for day in days:
        ymd = day.replace("-", "")
        for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
            fp = logs / name
            if fp.is_file():
                candidates.append((fp.stat().st_mtime, day, fp))

    # 3) 名前が違う/日付不明な pkl も新しい順で拾う
    if logs.is_dir():
        for fp in logs.glob("morning_bulk_races_*.pkl"):
            day = _day_from_name(fp.name)
            candidates.append((fp.stat().st_mtime, day, fp))

    # mtime 新しい順・ユニーク path
    seen: set[str] = set()
    ordered: list[tuple[str, Path]] = []
    for _mtime, day, fp in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = str(fp)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((day, fp))

    notes.append(
        "pkl_candidates="
        + ",".join(f"{d}:{p.name}" for d, p in ordered[:8])
    )

    for day, fp in ordered:
        races = _try_load_pkl(fp)
        if races:
            notes.append(f"loaded {fp.name} day={day} n={len(races)}")
            # day が変でも schedule_date は today を優先（開催日想定）
            use_day = today if day.startswith("20") else today
            # pkl 名の日付が today/近傍ならそれを使う
            if day in days:
                use_day = day
            return use_day, races, notes

    # 4) done flag だけある場合のヒント
    if logs.is_dir():
        flags = sorted(logs.glob("morning_bulk_done_*.flag"))
        notes.append("done_flags=" + ",".join(p.name for p in flags[-5:]))

    return today, {}, notes


def _publish_via_export(races: dict[str, Any], day: str) -> dict[str, Any]:
    from public_viewer.export_public_snapshot import (  # type: ignore
        build_public_snapshot,
        upload_json_object,
    )

    snap = build_public_snapshot(races=races, day_rows=None, schedule_date=day)
    if not isinstance(snap, dict):
        return {"ok": False, "error": "build_public_snapshot_bad_type"}
    snap.setdefault("schedule_date", day)
    # cleared が残らないように明示
    snap["cleared"] = False
    url, err = upload_json_object("snapshots/latest.json", snap)
    if err:
        return {"ok": False, "error": str(err), "via": "export_upload"}
    return {
        "ok": True,
        "via": "export_upload",
        "url": url,
        "schedule_date": day,
        "race_count": snap.get("race_count"),
        "venue_count": snap.get("venue_count"),
        "updated_at": snap.get("updated_at"),
    }


def _publish_via_hwm(force: bool = True) -> dict[str, Any]:
    from hwm import _publish_public_viewer_snapshot  # type: ignore

    _publish_public_viewer_snapshot(force=force)
    return {"ok": True, "via": "hwm._publish_public_viewer_snapshot", "force": force}


def run_publish(*, force: bool = True) -> dict[str, Any]:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _load_env(root)
    os.environ.setdefault("HWM_SERVER_AUTO", "1")
    os.environ.setdefault("HWM_SUBPROCESS_PREDICT", "1")

    day, races, notes = _load_races(root)
    if not races:
        return {
            "ok": False,
            "error": "empty_races_cache",
            "schedule_date": day,
            "root": str(root),
            "notes": notes,
        }

    try:
        import streamlit as st  # type: ignore

        if hasattr(st, "session_state"):
            st.session_state["races"] = races
    except Exception:
        pass

    errors: list[str] = []
    try:
        out = _publish_via_export(races, day)
        if out.get("ok"):
            out["n_races_cache"] = len(races)
            out["notes"] = notes
            return out
        errors.append(str(out.get("error")))
    except Exception as e:
        errors.append(f"export: {type(e).__name__}: {e}")

    try:
        out = _publish_via_hwm(force=force)
        out["n_races_cache"] = len(races)
        out["schedule_date"] = day
        out["export_errors"] = errors
        out["notes"] = notes
        return out
    except Exception as e:
        errors.append(f"hwm: {type(e).__name__}: {e}")

    return {
        "ok": False,
        "error": "all_publish_paths_failed",
        "errors": errors,
        "schedule_date": day,
        "n_races_cache": len(races),
        "notes": notes,
        "traceback": traceback.format_exc()[-2000:],
    }


def main() -> int:
    out = run_publish(force=True)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

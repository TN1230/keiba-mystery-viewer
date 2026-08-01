#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""朝一斉レースキャッシュから閲覧サイト latest.json を強制 publish する。

サーバー上:
  cd /opt/yokuumakun_auto-x && .venv/bin/python force_publish_public_snapshot.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


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


def _load_races(root: Path) -> tuple[str, dict[str, Any]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    day = ""
    try:
        from hwm_server_standalone import (  # type: ignore
            _load_morning_bulk_races_cache,
            effective_schedule_date_iso,
        )

        day = str(effective_schedule_date_iso())
        races = _load_morning_bulk_races_cache(day) or {}
        if races:
            return day, races
    except Exception:
        pass

    # フォールバック: 当日 pkl を直接読む
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import pickle

    day = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    ymd = day.replace("-", "")
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        fp = root / "logs" / name
        if not fp.is_file():
            continue
        with fp.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict) and data:
            return day, data
    return day, {}


def _publish_via_export(races: dict[str, Any], day: str) -> dict[str, Any]:
    from public_viewer.export_public_snapshot import (  # type: ignore
        build_public_snapshot,
        upload_json_object,
    )

    snap = build_public_snapshot(races=races, day_rows=None, schedule_date=day)
    if not isinstance(snap, dict):
        return {"ok": False, "error": "build_public_snapshot_bad_type"}
    snap.setdefault("schedule_date", day)
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

    day, races = _load_races(root)
    if not races:
        return {"ok": False, "error": "empty_races_cache", "schedule_date": day, "root": str(root)}

    # session_state を使う実装向けに最低限埋める
    try:
        import streamlit as st  # type: ignore

        if not hasattr(st, "session_state"):
            pass
        else:
            st.session_state["races"] = races
    except Exception:
        pass

    errors: list[str] = []
    try:
        out = _publish_via_export(races, day)
        if out.get("ok"):
            out["n_races_cache"] = len(races)
            return out
        errors.append(str(out.get("error")))
    except Exception as e:
        errors.append(f"export: {type(e).__name__}: {e}")

    try:
        out = _publish_via_hwm(force=force)
        out["n_races_cache"] = len(races)
        out["schedule_date"] = day
        out["export_errors"] = errors
        return out
    except Exception as e:
        errors.append(f"hwm: {type(e).__name__}: {e}")

    return {
        "ok": False,
        "error": "all_publish_paths_failed",
        "errors": errors,
        "schedule_date": day,
        "n_races_cache": len(races),
        "traceback": traceback.format_exc()[-2000:],
    }


def main() -> int:
    out = run_publish(force=True)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

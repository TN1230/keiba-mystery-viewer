#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正式 publish 経路（day_rows=Edge行 + build_public_snapshot）で latest を再公開する。

standalone は近似で、偏差/ホームズ/出馬表順/第3探偵が欠ける。
本スクリプトは hwm / export_public_snapshot の本番ヘルパを優先する。
"""

from __future__ import annotations

import inspect
import json
import os
import pickle
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
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
        for rel in ("server_deployment/hwm_runtime.env", "server_deployment/.env"):
            p = root / rel
            if p.is_file():
                load_dotenv(p, override=False)
    except Exception:
        pass


def _load_races(root: Path) -> tuple[str, dict[str, Any], list[str]]:
    notes: list[str] = []
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    day = datetime.now(_JST).strftime("%Y-%m-%d")
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
    except Exception as e:
        notes.append(f"helper_cache err={type(e).__name__}:{e}")

    ymd = day.replace("-", "")
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        fp = root / "logs" / name
        if not fp.is_file():
            continue
        with fp.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict) and data:
            notes.append(f"loaded {name} n={len(data)}")
            return day, data, notes
    return day, {}, notes


def _upload(path: str, payload: Any) -> str | None:
    try:
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        url, err = upload_json_object(path, payload)
        return err or url
    except Exception as e:
        return f"{type(e).__name__}:{e}"


def _dump_helpers() -> dict[str, Any]:
    out: dict[str, Any] = {"updated_at": datetime.now(_JST).isoformat(timespec="seconds")}
    try:
        from public_viewer import export_public_snapshot as mod  # type: ignore

        out["export_file"] = getattr(mod, "__file__", None)
        names = [
            "build_public_snapshot",
            "_race_public_from_row",
            "_matrix_row_public",
            "_morning_holmes_score_map",
            "_holmes_public_fields",
            "rank_edge_rows",
            "matrix_table_records",
            "_public_viewer_timing_fields",
            "ranking_line",
            "_logic_label_for_row",
        ]
        srcs: dict[str, str] = {}
        for n in names:
            fn = getattr(mod, n, None)
            if callable(fn):
                try:
                    srcs[n] = inspect.getsource(fn)[:80000]
                except Exception as e:
                    srcs[n] = f"<err {type(e).__name__}:{e}>"
        out["export_sources"] = srcs
        out["export_callables"] = sorted(
            n for n, v in vars(mod).items() if callable(v) and not n.startswith("__")
        )
    except Exception as e:
        out["export_err"] = f"{type(e).__name__}:{e}"

    try:
        import hwm  # type: ignore

        out["hwm_file"] = getattr(hwm, "__file__", None)
        for n in (
            "_publish_public_viewer_snapshot",
            "_build_day_rows",
            "build_day_rows",
            "_edge_rows_for_day",
            "_today_edge_rows",
            "_refresh_day_rows",
            "_rebuild_day_rows",
        ):
            fn = getattr(hwm, n, None)
            if callable(fn):
                try:
                    out.setdefault("hwm_sources", {})[n] = inspect.getsource(fn)[:80000]
                except Exception as e:
                    out.setdefault("hwm_sources", {})[n] = f"<err {type(e).__name__}:{e}>"
        # fuzzy list
        out["hwm_publishish"] = sorted(
            n
            for n in dir(hwm)
            if any(k in n.lower() for k in ("publish", "day_row", "edge", "snapshot", "holmes"))
        )[:80]
    except Exception as e:
        out["hwm_err"] = f"{type(e).__name__}:{e}"
    return out


def _set_session_races(races: dict[str, Any]) -> None:
    try:
        import streamlit as st  # type: ignore

        st.session_state["races"] = races
    except Exception:
        pass


def _try_call_builders(races: dict[str, Any], day: str, notes: list[str]) -> list[Any]:
    """本番コードから day_rows(Edge行) を得る。"""
    candidates: list[tuple[str, Callable[..., Any]]] = []

    try:
        import hwm  # type: ignore

        for name in dir(hwm):
            low = name.lower()
            if not any(k in low for k in ("day_row", "edge_row", "edge_rows", "ranking_row")):
                continue
            fn = getattr(hwm, name, None)
            if callable(fn):
                candidates.append((f"hwm.{name}", fn))
        pub = getattr(hwm, "_publish_public_viewer_snapshot", None)
        if callable(pub):
            # publish 自体は後で試す
            notes.append("hwm._publish_public_viewer_snapshot available")
    except Exception as e:
        notes.append(f"hwm_import err={type(e).__name__}:{e}")

    try:
        from public_viewer import export_public_snapshot as mod  # type: ignore

        for name in dir(mod):
            low = name.lower()
            if "edge" in low or "day_row" in low:
                fn = getattr(mod, name, None)
                if callable(fn):
                    candidates.append((f"export.{name}", fn))
    except Exception as e:
        notes.append(f"export_import err={type(e).__name__}:{e}")

    # dedicated helpers often used by UI
    for mod_name in ("race_day_ranking", "edge_ranking", "public_viewer.ranking", "ranking_core"):
        try:
            mod = __import__(mod_name, fromlist=["*"])
            for name in dir(mod):
                if "row" in name.lower() or "edge" in name.lower() or "rank" in name.lower():
                    fn = getattr(mod, name, None)
                    if callable(fn) and not name.startswith("_"):
                        candidates.append((f"{mod_name}.{name}", fn))
        except Exception:
            pass

    notes.append(f"builder_candidates={len(candidates)}")
    for label, fn in candidates[:40]:
        for kwargs in (
            lambda: fn(races),
            lambda: fn(races=races),
            lambda: fn(races, day),
            lambda: fn(races=races, schedule_date=day),
            lambda: fn(),
        ):
            try:
                rows = kwargs()
            except TypeError:
                continue
            except Exception as e:
                notes.append(f"{label} exc={type(e).__name__}:{e}"[:200])
                break
            if isinstance(rows, list) and rows and not isinstance(rows[0], dict):
                # attribute-style rows
                sample = rows[0]
                if hasattr(sample, "race_id") or hasattr(sample, "place"):
                    notes.append(f"got_rows via {label} n={len(rows)} type={type(sample).__name__}")
                    return rows
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "race_id" in rows[0]:
                notes.append(f"got_dict_rows via {label} n={len(rows)} (may be insufficient)")
    return []


def _publish_with_day_rows(races: dict[str, Any], day: str, day_rows: list[Any]) -> dict[str, Any]:
    from public_viewer.export_public_snapshot import (  # type: ignore
        build_public_snapshot,
        upload_json_object,
    )

    snap = build_public_snapshot(races=races, day_rows=day_rows, schedule_date=day)
    if not isinstance(snap, dict):
        return {"ok": False, "error": "bad_snap_type"}
    snap["cleared"] = False
    rc = int(snap.get("race_count") or 0)
    # quality gates
    venues = snap.get("venues") or []
    n_races = sum(len(v.get("races") or []) for v in venues if isinstance(v, dict))
    if rc <= 0 or n_races <= 0:
        return {
            "ok": False,
            "error": "official_empty_races",
            "race_count": rc,
            "n_races_listed": n_races,
        }
    # holmes / dev checks
    sample = None
    for v in venues:
        rs = v.get("races") or []
        if rs:
            sample = rs[0]
            break
    url, err = upload_json_object("snapshots/latest.json", snap)
    return {
        "ok": not err and rc > 0,
        "error": err,
        "url": url,
        "via": "official_build_public_snapshot",
        "schedule_date": day,
        "race_count": rc,
        "venue_count": snap.get("venue_count"),
        "updated_at": snap.get("updated_at"),
        "sample_dev": None if not sample else sample.get("dev"),
        "sample_holmes": None if not sample else sample.get("holmes_index"),
        "sample_marks": None if not sample else sample.get("marks"),
    }


def _publish_via_hwm() -> dict[str, Any]:
    from hwm import _publish_public_viewer_snapshot  # type: ignore

    _publish_public_viewer_snapshot(force=True)
    # verify
    import urllib.request

    with urllib.request.urlopen(
        "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
        "public-viewer/snapshots/latest.json",
        timeout=30,
    ) as resp:
        latest = json.loads(resp.read().decode("utf-8"))
    rc = int((latest or {}).get("race_count") or 0)
    return {
        "ok": rc > 0,
        "via": "hwm._publish_public_viewer_snapshot",
        "race_count": rc,
        "schedule_date": (latest or {}).get("schedule_date"),
        "updated_at": (latest or {}).get("updated_at"),
        "error": None if rc > 0 else "hwm_still_empty",
    }


def _quality_report(snap_url_check: bool = True) -> dict[str, Any]:
    import urllib.request

    with urllib.request.urlopen(
        "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
        "public-viewer/snapshots/latest.json",
        timeout=30,
    ) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    missing_h = 0
    long_dev = 0
    umaban_sorted = 0
    third_blank = 0
    watson_blank = 0
    n = 0
    for v in d.get("venues") or []:
        for r in v.get("races") or []:
            n += 1
            if not r.get("holmes_index"):
                missing_h += 1
            dev = r.get("dev")
            if isinstance(dev, float) and abs(dev * 10 - round(dev * 10)) > 1e-9 and len(str(dev)) > 6:
                long_dev += 1
            elif isinstance(dev, str) and "." in dev and len(dev.split(".")[-1]) > 2:
                long_dev += 1
            rows = ((r.get("shutuba") or {}).get("rows")) or []
            umas = [str(x.get("馬番")) for x in rows[:5]]
            if umas == sorted(umas, key=lambda x: int(x) if x.isdigit() else 99):
                # likely umaban order (weak)
                umaban_sorted += 1
            marks = r.get("marks") or {}
            if marks.get("ワ") in (None, "", "-"):
                watson_blank += 1
            cells = r.get("cells") or {}
            if (marks.get("ハ/ホプ") in (None, "", "-")) and (cells.get("ハ/ホプ") in (None, "", "-")):
                third_blank += 1
    return {
        "race_count": d.get("race_count"),
        "n_races": n,
        "missing_holmes": missing_h,
        "long_dev": long_dev,
        "likely_umaban_order": umaban_sorted,
        "watson_blank": watson_blank,
        "third_blank": third_blank,
        "updated_at": d.get("updated_at"),
        "ok_quality": missing_h == 0 and long_dev == 0 and n > 0,
    }


def run() -> dict[str, Any]:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _load_env(root)
    os.environ.setdefault("HWM_SERVER_AUTO", "1")
    os.environ.setdefault("HWM_SUBPROCESS_PREDICT", "1")

    notes: list[str] = []
    helpers = _dump_helpers()
    notes.append(f"helpers_upload={_upload('ops/publish_helpers_dump.json', helpers)}")

    day, races, load_notes = _load_races(root)
    notes.extend(load_notes)
    if not races:
        return {"ok": False, "error": "empty_races_cache", "notes": notes}

    _set_session_races(races)

    attempts: list[dict[str, Any]] = []

    # 1) official day_rows builders
    day_rows = _try_call_builders(races, day, notes)
    if day_rows:
        try:
            out = _publish_with_day_rows(races, day, day_rows)
            attempts.append(out)
            if out.get("ok"):
                q = _quality_report()
                out["quality"] = q
                out["notes"] = notes
                out["attempts"] = attempts
                _upload("ops/official_republish_last.json", out)
                return out
        except Exception as e:
            attempts.append({"ok": False, "error": f"official: {type(e).__name__}:{e}"})
            notes.append(attempts[-1]["error"])

    # 2) hwm publisher
    try:
        out = _publish_via_hwm()
        attempts.append(out)
        if out.get("ok"):
            q = _quality_report()
            out["quality"] = q
            out["notes"] = notes
            out["attempts"] = attempts
            _upload("ops/official_republish_last.json", out)
            if q.get("ok_quality"):
                return out
            notes.append("hwm_ok_but_quality_weak")
    except Exception as e:
        attempts.append({"ok": False, "error": f"hwm: {type(e).__name__}:{e}"})
        notes.append(attempts[-1]["error"])

    # 3) improved standalone
    try:
        from standalone_publish_from_cache import run as standalone_run

        out = standalone_run()
        attempts.append(out if isinstance(out, dict) else {"raw": str(out)})
        if isinstance(out, dict) and out.get("ok"):
            q = _quality_report()
            out["quality"] = q
            out["notes"] = notes + list(out.get("notes") or [])
            out["attempts"] = attempts
            out["via"] = "standalone_after_official_miss"
            _upload("ops/official_republish_last.json", out)
            return out
    except Exception as e:
        attempts.append({"ok": False, "error": f"standalone: {type(e).__name__}:{e}"})
        notes.append(traceback.format_exc()[-500:])

    out = {
        "ok": False,
        "error": "all_official_paths_failed",
        "notes": notes,
        "attempts": attempts,
        "schedule_date": day,
        "n_races_cache": len(races),
    }
    _upload("ops/official_republish_last.json", out)
    return out


def main() -> int:
    out = run()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Republish latest.json using the SAME helpers as Edge (hwm._publish / _race_public_from_row).

Preferred path: hwm._publish_public_viewer_snapshot_from_races(races)
Fallback: build Edge-like day_rows via _collect_day_edge_rows_from_races or
_build_race_edge_row_for_rinfo, then build_public_snapshot(day_rows=...).
"""
from __future__ import annotations

import importlib.util
import json
import os
import pickle
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple


def _root() -> Path:
    return Path(os.environ.get("YOKUUMAKUN_ROOT") or "/opt/yokuumakun_auto-x").expanduser().resolve()


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _jsonable(obj: Any, *, _seen: Optional[set] = None, depth: int = 0) -> Any:
    """Best-effort JSON conversion; drop cycles / non-serializable bits."""
    if depth > 8:
        return "<max_depth>"
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if _seen is None:
        _seen = set()
    oid = id(obj)
    if oid in _seen:
        return "<cycle>"
    if isinstance(obj, dict):
        _seen.add(oid)
        try:
            return {str(k): _jsonable(v, _seen=_seen, depth=depth + 1) for k, v in list(obj.items())[:80]}
        finally:
            _seen.discard(oid)
    if isinstance(obj, (list, tuple)):
        _seen.add(oid)
        try:
            return [_jsonable(v, _seen=_seen, depth=depth + 1) for v in list(obj)[:80]]
        finally:
            _seen.discard(oid)
    if isinstance(obj, SimpleNamespace):
        return _jsonable(vars(obj), _seen=_seen, depth=depth + 1)
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return repr(obj)[:240]


def _pick_cache(root: Path) -> Tuple[Optional[Path], Optional[date]]:
    logs = root / "logs"
    cands = sorted(logs.glob("morning_bulk_races_*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
    today = date.today()
    for p in cands:
        try:
            stem = p.stem.replace("morning_bulk_races_", "")
            d = date(int(stem[0:4]), int(stem[4:6]), int(stem[6:8]))
        except Exception:
            continue
        if d == today:
            return p, d
    if cands:
        p = cands[0]
        try:
            stem = p.stem.replace("morning_bulk_races_", "")
            d = date(int(stem[0:4]), int(stem[4:6]), int(stem[6:8]))
            return p, d
        except Exception:
            return p, today
    return None, None


def _load_races(path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        obj = pickle.load(f)
    if not isinstance(obj, dict):
        raise RuntimeError(f"cache is not dict: {type(obj)}")
    return obj


def _quality(snap: Dict[str, Any]) -> Dict[str, Any]:
    import re

    races = []
    for v in snap.get("venues") or []:
        races.extend(v.get("races") or [])
    if not races:
        return {"ok": False, "reason": "no_races"}
    bad_dev = 0
    for r in races:
        dev = r.get("dev")
        s = str(dev) if dev is not None else ""
        if "." in s and len(s.split(".")[-1]) > 1:
            bad_dev += 1
    holmes_vals = []
    for r in races:
        hi = str(r.get("holmes_index") or r.get("holmes") or "").strip()
        m = re.match(r"([0-9]+(?:\.[0-9]+)?)", hi)
        holmes_vals.append(m.group(1) if m else "")
    blank_h = sum(1 for h in holmes_vals if not h)
    identical_h = len(set(holmes_vals)) <= 1 and len(races) >= 3 and blank_h == 0
    sample = races[0]
    shutuba = sample.get("shutuba") or {}
    rows = shutuba.get("rows") if isinstance(shutuba, dict) else shutuba
    if not isinstance(rows, list):
        rows = []
    umas = [int(x.get("馬番") or 0) for x in rows[:8] if isinstance(x, dict)]
    ordered_by_umaban = umas == sorted(umas) and len(umas) >= 4
    marks = sample.get("marks") if isinstance(sample.get("marks"), dict) else {}
    marks_ok = any(str(marks.get(k) or "").strip() not in ("", "-") for k in ("ワ", "アイ", "ハ/ホプ"))
    cells = sample.get("cells") if isinstance(sample.get("cells"), dict) else {}
    cells_ok = any(str(v or "").strip() not in ("", "-") for v in cells.values()) if cells else False
    ok = (
        bad_dev == 0
        and blank_h == 0
        and not identical_h
        and not ordered_by_umaban
        and marks_ok
        and cells_ok
        and len(races) >= 12
    )
    return {
        "ok": ok,
        "race_count": len(races),
        "bad_dev": bad_dev,
        "blank_holmes": blank_h,
        "identical_holmes": identical_h,
        "holmes_sample": holmes_vals[:8],
        "ordered_by_umaban": ordered_by_umaban,
        "marks_ok": marks_ok,
        "cells_ok": cells_ok,
        "sample_dev": sample.get("dev"),
        "sample_holmes": sample.get("holmes_index") or sample.get("holmes"),
        "sample_shutuba0": rows[0] if rows else None,
    }


def main() -> int:
    root = _root()
    os.chdir(str(root))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    out: Dict[str, Any] = {"ok": False, "root": str(root), "attempts": []}

    cache_path, day = _pick_cache(root)
    out["cache_path"] = str(cache_path) if cache_path else None
    out["day"] = str(day) if day else None
    if cache_path is None or day is None:
        out["error"] = "no morning_bulk cache"
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 2

    races = _load_races(cache_path)
    out["n_races_cache"] = len(races)
    if not races:
        out["error"] = "empty cache"
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 3

    # Prefer the exact Edge one-shot publisher when present.
    try:
        hwm = _load_mod("hwm_official_publish", root / "hwm.py")
        if hasattr(hwm, "_publish_public_viewer_snapshot_from_races"):
            res = hwm._publish_public_viewer_snapshot_from_races(races)  # type: ignore[attr-defined]
            att = {"via": "_publish_public_viewer_snapshot_from_races", "result": _jsonable(res)}
            out["attempts"].append(att)
            if isinstance(res, dict) and res.get("ok"):
                out.update(
                    {
                        "ok": True,
                        "via": "_publish_public_viewer_snapshot_from_races",
                        "url": res.get("url"),
                        "race_count": res.get("race_count"),
                        "venue_count": res.get("venue_count"),
                        "updated_at": res.get("updated_at"),
                        "schedule_date": res.get("schedule_date"),
                    }
                )
                print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
                return 0
    except Exception as e:
        out["attempts"].append({"via": "_publish_public_viewer_snapshot_from_races", "error": repr(e)})

    # Build day_rows then call export path.
    try:
        export_mod = _load_mod("export_public_snapshot", root / "public_viewer" / "export_public_snapshot.py")
    except Exception as e:
        out["error"] = f"load export failed: {e!r}"
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 4

    day_rows: List[Any] = []
    via = ""

    try:
        hwm = sys.modules.get("hwm_official_publish") or _load_mod("hwm_official_publish", root / "hwm.py")
        if hasattr(hwm, "_collect_day_edge_rows_from_races"):
            day_rows = list(hwm._collect_day_edge_rows_from_races(races) or [])  # type: ignore[attr-defined]
            via = "_collect_day_edge_rows_from_races"
            out["attempts"].append({"via": via, "n_rows": len(day_rows)})
    except Exception as e:
        out["attempts"].append({"via": "_collect_day_edge_rows_from_races", "error": repr(e)})

    if not day_rows:
        try:
            hwm = sys.modules.get("hwm_official_publish") or _load_mod("hwm_official_publish", root / "hwm.py")
            build_one = getattr(hwm, "_build_race_edge_row_for_rinfo", None)
            if callable(build_one):
                for rid, rinfo in races.items():
                    if not isinstance(rinfo, dict):
                        continue
                    try:
                        row = build_one(str(rid), rinfo)
                    except Exception:
                        row = None
                    if row is not None:
                        day_rows.append(row)
                via = "_build_race_edge_row_for_rinfo"
                out["attempts"].append({"via": via, "n_rows": len(day_rows)})
        except Exception as e:
            out["attempts"].append({"via": "_build_race_edge_row_for_rinfo", "error": repr(e)})

    if not day_rows:
        out["error"] = "could not build Edge-compatible day_rows"
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 5

    # Sanity: first row should expose race_id / best_score like Edge.
    sample = day_rows[0]
    out["sample_row"] = {
        "type": type(sample).__name__,
        "race_id": getattr(sample, "race_id", None) or (sample.get("race_id") if isinstance(sample, dict) else None),
        "best_score": getattr(sample, "best_score", None) if not isinstance(sample, dict) else sample.get("best_score"),
        "has_rinfo": bool(getattr(sample, "rinfo", None) is not None) if not isinstance(sample, dict) else ("rinfo" in sample),
    }

    try:
        snap = export_mod.build_public_snapshot(  # type: ignore[attr-defined]
            schedule_date=day,
            venues_override=None,
            day_rows=day_rows,
            races_by_id=races,
            include_top5=True,
            cleared=False,
        )
        q = _quality(snap if isinstance(snap, dict) else {})
        out["quality"] = q
        if not q.get("ok"):
            out["error"] = "built snapshot failed quality checks"
            out["attempts"].append({"via": f"build_public_snapshot:{via}", "quality": q})
            # still try upload so operator can inspect; mark not-ok
        up = export_mod.upload_public_snapshot(snap)  # type: ignore[attr-defined]
        out["upload"] = _jsonable(up)
        if isinstance(up, dict) and up.get("ok") and q.get("ok"):
            out.update(
                {
                    "ok": True,
                    "via": f"build_public_snapshot:{via}",
                    "url": up.get("url"),
                    "race_count": snap.get("race_count"),
                    "venue_count": snap.get("venue_count"),
                    "updated_at": snap.get("updated_at"),
                    "schedule_date": snap.get("schedule_date"),
                }
            )
            print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
            return 0
        out["ok"] = bool(isinstance(up, dict) and up.get("ok") and q.get("ok"))
        out["error"] = out.get("error") or (up.get("error") if isinstance(up, dict) else "upload failed")
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 1 if not out["ok"] else 0
    except Exception as e:
        out["error"] = repr(e)
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 6


if __name__ == "__main__":
    raise SystemExit(main())

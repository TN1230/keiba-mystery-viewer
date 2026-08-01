#!/usr/bin/env python3
"""Republish latest.json using the SAME helpers as Edge (hwm._publish / _race_public_from_row).

Preferred path: hwm._publish_public_viewer_snapshot_from_races(races)
Fallback: build Edge-like day_rows via _collect_day_edge_rows_from_races or
_build_race_edge_row_for_rinfo, then build_public_snapshot(day_rows=...).
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import pickle
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple


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


def _filter_kwargs_for_callable(fn: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Drop kwargs that the target callable does not accept (server API drift)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    allowed = {
        name
        for name, p in sig.parameters.items()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return {k: v for k, v in kwargs.items() if k in allowed}


def _make_kwargs_filter_wrapper(orig: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return orig(*args, **_filter_kwargs_for_callable(orig, kwargs))

    wrapped._kwargs_filtered = True  # type: ignore[attr-defined]
    wrapped.__wrapped__ = orig  # type: ignore[attr-defined]
    try:
        wrapped.__name__ = getattr(orig, "__name__", "wrapped")  # type: ignore[attr-defined]
    except Exception:
        pass
    return wrapped


def _wrap_build_race_edge_row_attr(owner: Any, attr: str = "build_race_edge_row") -> bool:
    """Wrap owner.attr if it is an unwrapped build_race_edge_row callable."""
    try:
        fn = getattr(owner, attr, None)
    except Exception:
        return False
    if not callable(fn) or getattr(fn, "_kwargs_filtered", False):
        return False
    # Only wrap the real helper (or same-named imports); avoid unrelated attrs.
    name = getattr(fn, "__name__", "") or ""
    if name not in ("build_race_edge_row", "wrapped") and attr != "build_race_edge_row":
        return False
    if attr != "build_race_edge_row" and name != "build_race_edge_row":
        return False
    try:
        if isinstance(owner, dict):
            owner[attr] = _make_kwargs_filter_wrapper(fn)
        else:
            setattr(owner, attr, _make_kwargs_filter_wrapper(fn))
        return True
    except Exception:
        return False


def _patch_build_race_edge_row_kwargs() -> int:
    """Wrap loaded build_race_edge_row callables so unknown kwargs are ignored.

    Server drift example:
      TypeError: build_race_edge_row() got an unexpected keyword argument 'marks_baker'

    Also rewrites function __globals__ bindings (from X import build_race_edge_row),
    which module-level setattr alone does not fix.
    """
    n = 0
    seen_fn_ids: set[int] = set()

    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        if _wrap_build_race_edge_row_attr(mod, "build_race_edge_row"):
            n += 1
        # Patch collector helpers' globals that imported the bare function.
        for helper_name in (
            "_collect_day_edge_rows_from_races",
            "_build_race_edge_row_for_rinfo",
            "collect_day_edge_rows_from_races",
            "build_race_edge_row_for_rinfo",
        ):
            try:
                helper = getattr(mod, helper_name, None)
            except Exception:
                helper = None
            if not callable(helper):
                continue
            g = getattr(helper, "__globals__", None)
            if not isinstance(g, dict):
                continue
            for gname in ("build_race_edge_row", "_build_race_edge_row"):
                if gname not in g:
                    continue
                fn = g.get(gname)
                if not callable(fn) or getattr(fn, "_kwargs_filtered", False):
                    continue
                fid = id(fn)
                if fid in seen_fn_ids and getattr(g.get(gname), "_kwargs_filtered", False):
                    continue
                try:
                    g[gname] = _make_kwargs_filter_wrapper(fn)
                    seen_fn_ids.add(fid)
                    n += 1
                except Exception:
                    continue
            # Also wrap module-level _build_race_edge_row when present.
            if _wrap_build_race_edge_row_attr(mod, "_build_race_edge_row"):
                n += 1
    return n


def _try_direct_build_race_edge_rows(hwm: Any, races: Dict[str, Any]) -> Tuple[List[Any], Optional[str]]:
    """Call hwm.build_race_edge_row per race with filtered kwargs built from rinfo."""
    build = getattr(hwm, "build_race_edge_row", None)
    if not callable(build):
        return [], "no build_race_edge_row"
    # unwrap our filter wrapper to inspect the real signature for positional mapping
    target = getattr(build, "__wrapped__", build)
    try:
        sig = inspect.signature(target)
        param_names = list(sig.parameters.keys())
    except (TypeError, ValueError):
        param_names = []

    rows: List[Any] = []
    first_err: Optional[str] = None
    for rid, rinfo in races.items():
        if not isinstance(rinfo, dict):
            continue
        info = rinfo.get("info") if isinstance(rinfo.get("info"), dict) else None
        candidates: Dict[str, Any] = {
            "race_id": str(rid),
            "rid": str(rid),
            "rinfo": rinfo,
            "race": rinfo,
            # Edge helpers often expect schedule info (place/R/name), not full cache entry.
            "race_info": info if info is not None else rinfo,
            "info": info if info is not None else rinfo.get("info"),
            "marks_hunter": rinfo.get("hunter_marks") or rinfo.get("marks_hunter"),
            "marks_moriarty": rinfo.get("moriarty_marks") or rinfo.get("marks_moriarty"),
            "marks_baker": rinfo.get("baker_marks") or rinfo.get("marks_baker"),
            "marks_watson": rinfo.get("watson_marks") or rinfo.get("marks_watson"),
            "prediction": rinfo.get("prediction"),
            "pred": rinfo.get("prediction"),
            "df": rinfo.get("df"),
            "dev": rinfo.get("dev"),
            "grade": rinfo.get("grade"),
            "rank": rinfo.get("rank"),
            "hunter_mode": rinfo.get("hunter_mode"),
            "hunter_label": rinfo.get("hunter_label"),
        }
        args: List[Any] = []
        kwargs: Dict[str, Any] = {}
        used: set[str] = set()
        for name in param_names:
            p = sig.parameters[name]
            if p.kind == inspect.Parameter.VAR_POSITIONAL:
                continue
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                continue
            val = candidates.get(name, inspect.Parameter.empty)
            if val is inspect.Parameter.empty:
                continue
            if p.kind == inspect.Parameter.POSITIONAL_ONLY:
                args.append(val)
                used.add(name)
            elif p.kind == inspect.Parameter.KEYWORD_ONLY:
                kwargs[name] = val
                used.add(name)
            elif p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
                # Prefer kwargs after first two positionals (race_id, rinfo)
                if name in ("race_id", "rid", "rinfo", "race", "race_info") and len(args) < 2:
                    args.append(val)
                else:
                    kwargs[name] = val
                used.add(name)
        if not args and not kwargs:
            # blind common call shapes
            try:
                row = build(str(rid), rinfo)
            except TypeError:
                try:
                    row = build(rinfo)
                except Exception as e:
                    if first_err is None:
                        first_err = repr(e)
                    continue
            except Exception as e:
                if first_err is None:
                    first_err = repr(e)
                continue
        else:
            try:
                row = build(*args, **_filter_kwargs_for_callable(target, kwargs))
            except Exception as e:
                if first_err is None:
                    first_err = repr(e)
                continue
        if row is not None:
            rows.append(row)
    return rows, first_err


PREV_WEEK_REF_URL = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/snapshots/2026-07-26.json"
)


def _load_prev_week_holmes_ref() -> Dict[str, Any]:
    """前週（良品）スナップを参照し、ホームズ指数の妥当レンジを得る。"""
    import re
    import urllib.request

    out: Dict[str, Any] = {
        "ok": False,
        "url": PREV_WEEK_REF_URL,
        "min": 40.0,
        "max": 100.0,
        "n": 0,
        "unique": 0,
    }
    try:
        with urllib.request.urlopen(PREV_WEEK_REF_URL, timeout=20) as resp:
            snap = json.load(resp)
    except Exception as e:
        out["error"] = repr(e)
        return out
    vals: List[float] = []
    for v in snap.get("venues") or []:
        for r in v.get("races") or []:
            hi = str(r.get("holmes_index") or "").strip()
            m = re.match(r"([0-9]+(?:\.[0-9]+)?)", hi)
            if not m:
                continue
            try:
                vals.append(float(m.group(1)))
            except Exception:
                continue
    if not vals:
        out["error"] = "no_holmes_in_ref"
        return out
    # 前週の実測からフロアを少し緩める（ただし 25/5 等の誤値は依然弾く側で扱う）
    lo = max(30.0, min(vals) - 5.0)
    hi = min(100.0, max(vals) + 2.0)
    out.update(
        {
            "ok": True,
            "min": lo,
            "max": hi,
            "n": len(vals),
            "unique": len(set(vals)),
            "sample": vals[:8],
            "schedule_date": snap.get("schedule_date"),
            "schema_version": snap.get("schema_version"),
        }
    )
    return out


def _invoke_build_public_snapshot(
    export_mod: Any,
    *,
    day: Any,
    day_rows: List[Any],
    races: Dict[str, Any],
) -> Any:
    """Server export signature drift に耐える build_public_snapshot 呼び出し。

    実サーバー（ops dump）:
      build_public_snapshot(*, races, day_rows, schedule_date=None)
    旧想定:
      races_by_id= / venues_override= / include_top5= / cleared=
    """
    fn = getattr(export_mod, "build_public_snapshot")
    day_s = str(day) if day is not None else None
    candidates: Dict[str, Any] = {
        "races": races,
        "races_by_id": races,
        "day_rows": day_rows,
        "schedule_date": day_s,
        "venues_override": None,
        "include_top5": True,
        "cleared": False,
    }
    try:
        sig = inspect.signature(fn)
        params = sig.parameters
    except (TypeError, ValueError):
        # 既知の現行シグネチャ
        return fn(races=races, day_rows=day_rows, schedule_date=day_s)

    kwargs: Dict[str, Any] = {}
    for name in params:
        if name in candidates:
            kwargs[name] = candidates[name]
    # races が必須な現行 API で races_by_id だけ渡していた事故を防ぐ
    if "races" in params and "races" not in kwargs:
        kwargs["races"] = races
    if "day_rows" in params and "day_rows" not in kwargs:
        kwargs["day_rows"] = day_rows
    if "schedule_date" in params and "schedule_date" not in kwargs:
        kwargs["schedule_date"] = day_s
    return fn(**_filter_kwargs_for_callable(fn, kwargs))


def _upload_ops_json(export_mod: Any, rel: str, payload: Dict[str, Any]) -> None:
    try:
        up = getattr(export_mod, "upload_json_object", None)
        if callable(up):
            up(rel, payload)
    except Exception:
        pass


def _upload_latest_snapshot(export_mod: Any, snap: Dict[str, Any]) -> Dict[str, Any]:
    """Upload latest.json. Server has upload_json_object, not upload_public_snapshot."""
    up = getattr(export_mod, "upload_public_snapshot", None)
    if callable(up):
        try:
            res = up(snap)
            if isinstance(res, dict):
                return res
            if isinstance(res, tuple) and len(res) >= 2:
                url, err = res[0], res[1]
                return {"ok": not err, "url": url, "error": err}
            return {"ok": True, "result": _jsonable(res)}
        except Exception as e:
            # fall through to upload_json_object
            last_err = repr(e)
    else:
        last_err = "no upload_public_snapshot"

    upj = getattr(export_mod, "upload_json_object", None)
    if callable(upj):
        try:
            url, err = upj("snapshots/latest.json", snap)
            return {"ok": not err, "url": url, "error": err, "via": "upload_json_object"}
        except Exception as e:
            return {"ok": False, "error": repr(e), "via": "upload_json_object"}
    return {"ok": False, "error": last_err or "no upload helper"}


def _dump_export_helpers(export_mod: Any) -> Dict[str, Any]:
    import inspect as _inspect

    dumped: Dict[str, Any] = {}
    for name in (
        "build_public_snapshot",
        "_holmes_public_fields",
        "_morning_holmes_score_map",
        "_race_public_from_row",
        "_matrix_row_public",
    ):
        fn = getattr(export_mod, name, None)
        if not callable(fn):
            continue
        try:
            src = _inspect.getsource(fn)
        except Exception as e:
            dumped[name] = {"error": repr(e)}
            continue
        payload = {
            "updated_at": str(date.today()),
            "func": name,
            "source": src[:120000],
            "module_file": getattr(export_mod, "__file__", None),
        }
        _upload_ops_json(export_mod, f"ops/{name}_source.py.json", payload)
        dumped[name] = {"bytes": len(src), "file": payload["module_file"]}
    return dumped


def _fmt_bataiju_int(v: Any) -> str:
    import re

    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            x = float(v)
        except Exception:
            return ""
        if x != x:
            return ""
        return str(int(round(x)))
    s = str(v).strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        try:
            return str(int(round(float(s))))
        except Exception:
            return s
    m = re.match(r"^(-?\d+(?:\.\d+)?)(.*)$", s)
    if m:
        try:
            return str(int(round(float(m.group(1))))) + m.group(2)
        except Exception:
            return s
    return s


def _fmt_kinryo_display(v: Any) -> str:
    """斤量: 0.5kg 端数なしは整数、0.5 は小数1桁。"""
    if v is None or v == "":
        return ""
    try:
        x = float(v)
    except Exception:
        return str(v).strip()
    if x != x:
        return ""
    half = round(x * 2.0) / 2.0
    if abs(x - half) > 1e-6:
        if abs(x - round(x)) < 1e-6:
            return str(int(round(x)))
        return f"{x:.1f}".rstrip("0").rstrip(".")
    if abs(half - round(half)) < 1e-6:
        return str(int(round(half)))
    return f"{half:.1f}"


def _sui_short(v: Any) -> str:
    s0 = str(v or "").strip()
    if not s0 or s0 == "-":
        return "-"
    s = s0.split("（")[0].split("(")[0].strip() or s0
    blob = s0
    if "ホプ" in blob or "hopkins" in blob.lower():
        return "ホプキンス"
    if "モーリ" in blob:
        return "モーリアティ"
    if "ワトソン" in blob or s.lower() == "watson":
        return "ワトソン"
    if "アイ" in blob or s.lower() == "irene":
        return "アイリーン"
    if "ハンター" in blob or s.lower() == "hunter":
        return "ハンター"
    return s


def _normalize_matrix_sui(snap: Dict[str, Any]) -> int:
    """マトリクス『推』を前週同様の短名にそろえる。"""
    n = 0
    for v in snap.get("venues") or []:
        for m in v.get("matrix") or []:
            if not isinstance(m, dict) or "sui" not in m:
                continue
            new_s = _sui_short(m.get("sui"))
            if m.get("sui") != new_s:
                m["sui"] = new_s
                n += 1
        for r in v.get("races") or []:
            if not isinstance(r, dict):
                continue
            # best_logic が日本語長文のとき key を正規化
            bl = r.get("best_logic")
            lab = r.get("best_logic_label")
            blob = f"{bl} {lab}"
            if isinstance(bl, str) and ("（" in bl or "ホプキンス" in bl or "ハンター（" in bl):
                if "ホプ" in blob:
                    r["best_logic"] = "hunter"
                    r["best_logic_label"] = "ホプキンス（新馬戦特化）"
                    n += 1
                elif "ハンター" in blob:
                    r["best_logic"] = "hunter"
                    r["best_logic_label"] = "ハンター（夏競馬特化）"
                    n += 1
    return n


def _normalize_shutuba_bataiju(snap: Dict[str, Any]) -> int:
    """出馬表の馬体重・斤量表示を正規化（528.0→528, 57.0→57, 55.5→55.5）。"""
    n = 0
    for v in snap.get("venues") or []:
        for r in v.get("races") or []:
            shutuba = r.get("shutuba") if isinstance(r, dict) else None
            if not isinstance(shutuba, dict):
                continue
            rows = shutuba.get("rows")
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if "馬体重" in row:
                    new_v = _fmt_bataiju_int(row.get("馬体重"))
                    if row.get("馬体重") != new_v:
                        row["馬体重"] = new_v
                        n += 1
                if "斤量" in row:
                    new_k = _fmt_kinryo_display(row.get("斤量"))
                    if row.get("斤量") != new_k:
                        row["斤量"] = new_k
                        n += 1
    return n


def _enrich_snap_holmes_from_helpers(
    export_mod: Any,
    snap: Dict[str, Any],
    races: Dict[str, Any],
    day_rows: List[Any],
) -> Dict[str, Any]:
    """blank ホームズを morning map / Edge best_score + 正式ヘルパーで埋める。"""
    import re

    morning_map: Dict[str, Any] = {}
    try:
        mp_fn = getattr(export_mod, "_morning_holmes_score_map", None)
        if callable(mp_fn):
            morning_map = dict(mp_fn(races) or {})
    except Exception:
        morning_map = {}

    edge_best: Dict[str, float] = {}
    for row in day_rows or []:
        rid = str(getattr(row, "race_id", None) or (row.get("race_id") if isinstance(row, dict) else "") or "")
        if not rid:
            continue
        raw = getattr(row, "best_score", None) if not isinstance(row, dict) else row.get("best_score")
        try:
            edge_best[rid] = float(raw)
        except Exception:
            continue

    hfields_fn = getattr(export_mod, "_holmes_public_fields", None)
    filled = 0
    for v in snap.get("venues") or []:
        for r in v.get("races") or []:
            if not isinstance(r, dict):
                continue
            hi = str(r.get("holmes_index") or "").strip()
            if hi:
                # "25" / "5" など前週参照で明らかに壊れている値は再計算対象
                m = re.match(r"([0-9]+(?:\.[0-9]+)?)", hi)
                if m and float(m.group(1)) >= 40.0:
                    continue
            rid = str(r.get("race_id") or "")
            morning = morning_map.get(rid)
            latest = edge_best.get(rid)
            fields: Optional[Dict[str, Any]] = None
            if callable(hfields_fn):
                try:
                    fields = hfields_fn(latest if latest is not None else 0.0, morning)
                except Exception:
                    fields = None
            if isinstance(fields, dict) and str(fields.get("holmes_index") or "").strip():
                for k in (
                    "holmes_index",
                    "holmes_index_display",
                    "morning_holmes_index",
                    "holmes_index_delta",
                ):
                    if k in fields and fields[k] is not None:
                        r[k] = fields[k]
                filled += 1
                continue
            # ヘルパー無し: morning / edge を直接（40+ のみ）
            for cand in (morning, latest):
                try:
                    x = float(cand)
                except Exception:
                    continue
                if 40.0 <= x <= 100.0:
                    s = str(int(round(x))) if abs(x - round(x)) < 1e-6 else f"{x:.1f}".rstrip("0").rstrip(".")
                    r["holmes_index"] = s
                    r["morning_holmes_index"] = s if morning is not None else r.get("morning_holmes_index")
                    filled += 1
                    break
    return {"filled": filled, "morning_map_n": len(morning_map), "edge_best_n": len(edge_best)}


def _quality(snap: Dict[str, Any], *, ref: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
    # 前週良品は unique が多い。identical や 5/25 固定は不合格。
    bad_const = False
    if identical_h and holmes_vals and holmes_vals[0] in {"5", "25", "0"}:
        bad_const = True
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

    def _cell_vals(key: str) -> List[str]:
        out: List[str] = []
        for r in races:
            c = r.get("cells") if isinstance(r.get("cells"), dict) else {}
            out.append(str(c.get(key) or "").strip())
        return out

    watson_cells = _cell_vals("ワ")
    irene_cells = _cell_vals("アイ")
    watson_present = [x for x in watson_cells if x and x != "-"]
    irene_present = [x for x in irene_cells if x and x != "-"]
    # 前週良品では評価帯がレースごとに分かれる。全同一の固定文言は standalone 劣化の典型。
    identical_watson = len(set(watson_present)) <= 1 and len(watson_present) >= max(8, len(races) // 2)
    identical_irene = len(set(irene_present)) <= 1 and len(irene_present) >= max(8, len(races) // 2)
    placeholder_cells = False
    if identical_watson and watson_present and watson_present[0] in {"様子・中位帯", "様子・印あり"}:
        placeholder_cells = True
    if identical_irene and irene_present and irene_present[0] in {"様子・様子見"}:
        placeholder_cells = True

    # ホームズ推: マトリクスは短名。長文や key 生値が残っていたら異常。
    long_sui = 0
    blank_sui = 0
    sui_vals: List[str] = []
    for v in snap.get("venues") or []:
        for m in v.get("matrix") or []:
            if not isinstance(m, dict):
                continue
            sui = str(m.get("sui") or "").strip()
            if not sui or sui == "-":
                blank_sui += 1
            else:
                sui_vals.append(sui)
            if "（" in sui or "(" in sui or sui in {"watson", "irene", "hunter", "moriarty", "hope"}:
                long_sui += 1

    ok = (
        bad_dev == 0
        and blank_h == 0
        and not identical_h
        and not bad_const
        and not ordered_by_umaban
        and marks_ok
        and cells_ok
        and not identical_watson
        and not identical_irene
        and not placeholder_cells
        and long_sui == 0
        and blank_sui == 0
        and len(races) >= 12
    )
    return {
        "ok": ok,
        "race_count": len(races),
        "bad_dev": bad_dev,
        "blank_holmes": blank_h,
        "identical_holmes": identical_h,
        "bad_const_holmes": bad_const,
        "holmes_sample": holmes_vals[:8],
        "ordered_by_umaban": ordered_by_umaban,
        "marks_ok": marks_ok,
        "cells_ok": cells_ok,
        "identical_watson_cells": identical_watson,
        "identical_irene_cells": identical_irene,
        "placeholder_cells": placeholder_cells,
        "watson_cell_sample": watson_present[:6],
        "irene_cell_sample": irene_present[:6],
        "sample_dev": sample.get("dev"),
        "sample_holmes": sample.get("holmes_index") or sample.get("holmes"),
        "sample_cells": cells,
        "sample_best_logic": sample.get("best_logic"),
        "sample_best_logic_label": sample.get("best_logic_label"),
        "long_sui": long_sui,
        "blank_sui": blank_sui,
        "sui_sample": sui_vals[:8],
        "sample_shutuba0": rows[0] if rows else None,
        "prev_week_ref": {
            "ok": bool(ref and ref.get("ok")),
            "min": (ref or {}).get("min"),
            "max": (ref or {}).get("max"),
            "unique": (ref or {}).get("unique"),
            "schedule_date": (ref or {}).get("schedule_date"),
        },
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

    # Ensure hwm (and its imports) are loaded, then wrap build_race_edge_row so
    # collectors that pass marks_baker= do not TypeError on older signatures.
    try:
        hwm = sys.modules.get("hwm_official_publish") or _load_mod("hwm_official_publish", root / "hwm.py")
    except Exception as e:
        out["attempts"].append({"via": "load_hwm_for_day_rows", "error": repr(e)})
        hwm = None

    patched_n = _patch_build_race_edge_row_kwargs()
    out["attempts"].append({"via": "patch_build_race_edge_row_kwargs", "patched": patched_n})

    if hwm is not None and hasattr(hwm, "_collect_day_edge_rows_from_races"):
        try:
            day_rows = list(hwm._collect_day_edge_rows_from_races(races) or [])  # type: ignore[attr-defined]
            via = "_collect_day_edge_rows_from_races"
            out["attempts"].append({"via": via, "n_rows": len(day_rows)})
        except Exception as e:
            out["attempts"].append({"via": "_collect_day_edge_rows_from_races", "error": repr(e)})
            # Collect often imports edge helpers mid-call; wrap then retry once.
            patched_after = _patch_build_race_edge_row_kwargs()
            out["attempts"].append(
                {"via": "patch_build_race_edge_row_kwargs_after_collect", "patched": patched_after}
            )
            try:
                day_rows = list(hwm._collect_day_edge_rows_from_races(races) or [])  # type: ignore[attr-defined]
                via = "_collect_day_edge_rows_from_races_retry"
                out["attempts"].append({"via": via, "n_rows": len(day_rows)})
            except Exception as e2:
                out["attempts"].append(
                    {"via": "_collect_day_edge_rows_from_races_retry", "error": repr(e2)}
                )

    if not day_rows and hwm is not None:
        try:
            build_one = getattr(hwm, "_build_race_edge_row_for_rinfo", None)
            if callable(build_one):
                first_err: Optional[str] = None
                for rid, rinfo in races.items():
                    if not isinstance(rinfo, dict):
                        continue
                    try:
                        row = build_one(str(rid), rinfo)
                    except Exception as e:
                        if first_err is None:
                            first_err = repr(e)
                        row = None
                    if row is not None:
                        day_rows.append(row)
                via = "_build_race_edge_row_for_rinfo"
                out["attempts"].append(
                    {"via": via, "n_rows": len(day_rows), "first_error": first_err}
                )
        except Exception as e:
            out["attempts"].append({"via": "_build_race_edge_row_for_rinfo", "error": repr(e)})

    if not day_rows and hwm is not None:
        # Re-patch in case for_rinfo loaded more modules
        patched_n2 = _patch_build_race_edge_row_kwargs()
        direct_rows, direct_err = _try_direct_build_race_edge_rows(hwm, races)
        out["attempts"].append(
            {
                "via": "direct_build_race_edge_row",
                "n_rows": len(direct_rows),
                "first_error": direct_err,
                "patched_extra": patched_n2,
            }
        )
        if direct_rows:
            day_rows = direct_rows
            via = "direct_build_race_edge_row"

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

    # 前週良品スナップを参照（レンジ・unique の目安）
    ref = _load_prev_week_holmes_ref()
    out["prev_week_ref"] = _jsonable(ref)
    out["export_helpers"] = _jsonable(_dump_export_helpers(export_mod))

    try:
        # シグネチャ検査（診断）
        try:
            out["build_public_snapshot_sig"] = str(inspect.signature(export_mod.build_public_snapshot))
        except Exception as e:
            out["build_public_snapshot_sig"] = repr(e)

        snap = _invoke_build_public_snapshot(
            export_mod, day=day, day_rows=day_rows, races=races
        )
        if not isinstance(snap, dict):
            out["error"] = f"build_public_snapshot returned {type(snap)}"
            _upload_ops_json(export_mod, "ops/official_republish_last.json", out)
            print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
            return 6

        enrich = _enrich_snap_holmes_from_helpers(export_mod, snap, races, day_rows)
        out["attempts"].append({"via": "enrich_holmes_from_helpers", **enrich})
        bataiju_n = _normalize_shutuba_bataiju(snap)
        out["attempts"].append({"via": "normalize_shutuba_bataiju", "changed": bataiju_n})
        sui_n = _normalize_matrix_sui(snap)
        out["attempts"].append({"via": "normalize_matrix_sui", "changed": sui_n})

        q = _quality(snap, ref=ref)
        out["quality"] = q
        if not q.get("ok"):
            out["error"] = "built snapshot failed quality checks"
            out["attempts"].append({"via": f"build_public_snapshot:{via}", "quality": q})
            # still try upload so operator can inspect; mark not-ok
        up = _upload_latest_snapshot(export_mod, snap)
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
            _upload_ops_json(export_mod, "ops/official_republish_last.json", out)
            print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
            return 0
        out["ok"] = bool(isinstance(up, dict) and up.get("ok") and q.get("ok"))
        out["error"] = out.get("error") or (up.get("error") if isinstance(up, dict) else "upload failed")
        _upload_ops_json(export_mod, "ops/official_republish_last.json", out)
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 1 if not out["ok"] else 0
    except Exception as e:
        out["error"] = repr(e)
        _upload_ops_json(export_mod, "ops/official_republish_last.json", out)
        print(json.dumps(_jsonable(out), ensure_ascii=False, indent=2))
        return 6


if __name__ == "__main__":
    raise SystemExit(main())

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
    for rel in (
        "server_deployment/hwm_runtime.env",
        "server_deployment/.env",
        ".env.local",
    ):
        rt = root / rel
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
    stem = name.replace("morning_bulk_races_", "").replace(".pkl", "")
    if len(stem) == 8 and stem.isdigit():
        return f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}"
    return stem


def _load_races(root: Path) -> tuple[str, dict[str, Any], list[str]]:
    notes: list[str] = []
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

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

    if logs.is_dir():
        for fp in logs.glob("morning_bulk_races_*.pkl"):
            day = _day_from_name(fp.name)
            candidates.append((fp.stat().st_mtime, day, fp))

    seen: set[str] = set()
    ordered: list[tuple[str, Path]] = []
    for _mtime, day, fp in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = str(fp)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((day, fp))

    notes.append(
        "pkl_candidates=" + ",".join(f"{d}:{p.name}" for d, p in ordered[:8])
    )

    for day, fp in ordered:
        races = _try_load_pkl(fp)
        if races:
            notes.append(f"loaded {fp.name} day={day} n={len(races)}")
            use_day = today if day.startswith("20") else today
            if day in days:
                use_day = day
            return use_day, races, notes

    if logs.is_dir():
        flags = sorted(logs.glob("morning_bulk_done_*.flag"))
        notes.append("done_flags=" + ",".join(p.name for p in flags[-5:]))

    return today, {}, notes


def _race_info(rinfo: Any) -> dict[str, Any]:
    if not isinstance(rinfo, dict):
        return {}
    info = rinfo.get("info")
    return info if isinstance(info, dict) else {}


def _day_rows_from_races(races: dict[str, Any]) -> list[dict[str, Any]]:
    """build_public_snapshot は day_rows=None だと会場殻だけ出して races を落とすことがある。"""
    rows: list[dict[str, Any]] = []
    for rid in sorted(races.keys(), key=str):
        rinfo = races.get(rid)
        if not isinstance(rinfo, dict):
            continue
        info = _race_info(rinfo)
        place = info.get("place") or rinfo.get("place") or ""
        r_no = info.get("R") or rinfo.get("R") or ""
        name = info.get("name") or rinfo.get("race_name") or rinfo.get("name") or ""
        start = info.get("start_time") or rinfo.get("start_time") or ""
        row = {
            "race_id": str(rid),
            "id": str(rid),
            "place": place,
            "会場": place,
            "R": r_no,
            "レース": r_no,
            "name": name,
            "race_name": name,
            "start_time": start,
            "発走": start,
        }
        # info の素のキーも残す（実装差吸収）
        for k, v in info.items():
            if k not in row:
                row[k] = v
        rows.append(row)
    return rows


def _sample_race_diag(races: dict[str, Any]) -> dict[str, Any]:
    if not races:
        return {"n": 0}
    rid = sorted(races.keys(), key=str)[0]
    rinfo = races.get(rid)
    out: dict[str, Any] = {"n": len(races), "sample_id": str(rid)}
    if not isinstance(rinfo, dict):
        out["sample_type"] = type(rinfo).__name__
        return out
    out["sample_keys"] = sorted(str(k) for k in rinfo.keys())
    info = _race_info(rinfo)
    out["info_keys"] = sorted(str(k) for k in info.keys()) if info else []
    out["has_prediction"] = rinfo.get("prediction") is not None
    out["prediction_type"] = type(rinfo.get("prediction")).__name__
    out["has_df"] = rinfo.get("df") is not None
    out["predicted_at"] = rinfo.get("predicted_at")
    out["place"] = info.get("place") or rinfo.get("place")
    out["R"] = info.get("R") or rinfo.get("R")
    return out


def _snap_ok(snap: dict[str, Any], n_cache: int) -> bool:
    try:
        rc = int(snap.get("race_count") or 0)
    except Exception:
        rc = 0
    if rc > 0:
        return True
    # 会場殻だけの成功は失敗扱い（キャッシュがあるとき）
    return n_cache <= 0


def _publish_via_export(
    races: dict[str, Any], day: str, *, day_rows: list[Any] | None
) -> dict[str, Any]:
    from public_viewer.export_public_snapshot import (  # type: ignore
        build_public_snapshot,
        upload_json_object,
    )

    snap = build_public_snapshot(
        races=races, day_rows=day_rows, schedule_date=day
    )
    if not isinstance(snap, dict):
        return {"ok": False, "error": "build_public_snapshot_bad_type"}
    snap.setdefault("schedule_date", day)
    snap["cleared"] = False
    try:
        from race_course_distance import enrich_snapshot_with_course_distance

        enriched = enrich_snapshot_with_course_distance(snap, races)
    except Exception:
        enriched = 0
    try:
        from race_pace_label import enrich_snapshot_with_pace_label

        pace_enriched = enrich_snapshot_with_pace_label(snap, races)
    except Exception:
        pace_enriched = 0
    meta = {
        "via": "export_upload",
        "schedule_date": day,
        "race_count": snap.get("race_count"),
        "venue_count": snap.get("venue_count"),
        "updated_at": snap.get("updated_at"),
        "day_rows_n": len(day_rows or []),
        "day_rows_is_none": day_rows is None,
        "course_distance_enriched": enriched,
        "pace_label_enriched": pace_enriched,
    }
    if not _snap_ok(snap, len(races)):
        meta["ok"] = False
        meta["error"] = "empty_snapshot_race_count"
        # 中身のヒント
        venues = snap.get("venues") if isinstance(snap.get("venues"), list) else []
        meta["venue_race_lens"] = [
            {
                "place": (v or {}).get("place"),
                "n": len((v or {}).get("races") or []),
            }
            for v in venues[:8]
            if isinstance(v, dict)
        ]
        return meta

    url, err = upload_json_object("snapshots/latest.json", snap)
    if err:
        meta["ok"] = False
        meta["error"] = str(err)
        return meta
    meta["ok"] = True
    meta["url"] = url
    return meta


def _publish_via_hwm(force: bool = True) -> dict[str, Any]:
    from hwm import _publish_public_viewer_snapshot  # type: ignore

    _publish_public_viewer_snapshot(force=force)
    return {"ok": True, "via": "hwm._publish_public_viewer_snapshot", "force": force}


def _parse_predicted_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_JST)
        return dt.astimezone(_JST)
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if 1_000_000_000 <= ts < 10_000_000_000:
                return datetime.fromtimestamp(ts, tz=_JST)
        except Exception:
            return None
    s = str(value).strip()
    if not s:
        return None
    try:
        ts = float(s)
        if 1_000_000_000 <= ts < 10_000_000_000:
            return datetime.fromtimestamp(ts, tz=_JST)
    except Exception:
        pass
    s2 = s.replace("T", " ").replace("Z", "")
    if "+" in s2[10:]:
        s2 = s2.split("+", 1)[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s2[:19], fmt).replace(tzinfo=_JST)
        except Exception:
            continue
    return None


def _max_predicted_at(races_or_snap: Any, *, public: bool = False) -> datetime | None:
    best: datetime | None = None
    items: list[Any]
    if public and isinstance(races_or_snap, dict):
        items = []
        for v in races_or_snap.get("venues") or []:
            if isinstance(v, dict):
                items.extend(v.get("races") or [])
    elif isinstance(races_or_snap, dict):
        items = list(races_or_snap.values())
    else:
        items = []
    for r in items:
        if not isinstance(r, dict):
            continue
        dt = _parse_predicted_at(r.get("predicted_at"))
        if dt and (best is None or dt > best):
            best = dt
    return best


def _hwm_reflects_cache(latest: dict[str, Any], races: dict[str, Any]) -> tuple[bool, str]:
    """hwm 経路は成功を返しても直前の predicted_at を載せないことがある。"""
    cache_max = _max_predicted_at(races, public=False)
    pub_max = _max_predicted_at(latest, public=True)
    if cache_max is None:
        return True, "no_cache_predicted_at"
    if pub_max is None:
        return False, f"public_missing_predicted_at cache={cache_max.isoformat()}"
    if cache_max > pub_max + timedelta(seconds=45):
        return (
            False,
            f"public_pred_stale cache={cache_max.isoformat()} public={pub_max.isoformat()}",
        )
    return True, "predicted_at_ok"


def _upload_diag(payload: dict[str, Any]) -> str | None:
    try:
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        url, err = upload_json_object("ops/force_publish_last.json", payload)
        if err:
            return f"diag_upload_err={err}"
        return f"diag_url={url}"
    except Exception as e:
        return f"diag_upload_exc={type(e).__name__}:{e}"


def _try_upload_export_source() -> str | None:
    try:
        import inspect

        from public_viewer import export_public_snapshot as mod  # type: ignore

        src = inspect.getsource(mod.build_public_snapshot)
        payload = {
            "updated_at": datetime.now(_JST).isoformat(timespec="seconds"),
            "func": "build_public_snapshot",
            "source": src[:120000],
            "module_file": getattr(mod, "__file__", None),
        }
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        url, err = upload_json_object("ops/build_public_snapshot_source.py.json", payload)
        if err:
            return f"source_upload_err={err}"
        return f"source_url={url}"
    except Exception as e:
        return f"source_upload_exc={type(e).__name__}:{e}"


def run_publish(*, force: bool = True) -> dict[str, Any]:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _load_env(root)
    os.environ.setdefault("HWM_SERVER_AUTO", "1")
    os.environ.setdefault("HWM_SUBPROCESS_PREDICT", "1")

    day, races, notes = _load_races(root)
    diag = _sample_race_diag(races)
    notes.append(f"sample={json.dumps(diag, ensure_ascii=False, default=str)[:800]}")

    if not races:
        out = {
            "ok": False,
            "error": "empty_races_cache",
            "schedule_date": day,
            "root": str(root),
            "notes": notes,
        }
        notes.append(str(_upload_diag(out)))
        return out

    try:
        import streamlit as st  # type: ignore

        if hasattr(st, "session_state"):
            st.session_state["races"] = races
    except Exception:
        pass

    day_rows = _day_rows_from_races(races)
    notes.append(f"day_rows_built n={len(day_rows)}")
    notes.append(str(_try_upload_export_source()))

    errors: list[str] = []
    attempts: list[dict[str, Any]] = []

    # 1) day_rows 付き export（本命）
    try:
        out = _publish_via_export(races, day, day_rows=day_rows)
        attempts.append(dict(out))
        if out.get("ok"):
            out["n_races_cache"] = len(races)
            out["notes"] = notes
            out["attempts"] = attempts
            notes.append(str(_upload_diag(out)))
            return out
        errors.append(str(out.get("error")))
    except Exception as e:
        errors.append(f"export_day_rows: {type(e).__name__}: {e}")
        attempts.append({"ok": False, "error": errors[-1]})

    # 2) day_rows=None（従来・比較用）
    try:
        out = _publish_via_export(races, day, day_rows=None)
        attempts.append(dict(out))
        if out.get("ok"):
            out["n_races_cache"] = len(races)
            out["notes"] = notes
            out["attempts"] = attempts
            notes.append(str(_upload_diag(out)))
            return out
        errors.append(str(out.get("error")))
    except Exception as e:
        errors.append(f"export_none: {type(e).__name__}: {e}")
        attempts.append({"ok": False, "error": errors[-1]})

    # 3) hwm 経路（UI と同じ）— 成功でも predicted_at が古いなら不合格にして続行
    try:
        out = _publish_via_hwm(force=force)
        # hwm は戻り値が薄いので latest を確認
        try:
            import urllib.request

            with urllib.request.urlopen(
                "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
                "public-viewer/snapshots/latest.json",
                timeout=30,
            ) as resp:
                latest = json.loads(resp.read().decode("utf-8"))
            rc = int((latest or {}).get("race_count") or 0)
            out["race_count"] = rc
            out["schedule_date_latest"] = (latest or {}).get("schedule_date")
            if rc <= 0:
                out["ok"] = False
                out["error"] = "hwm_publish_still_empty"
            else:
                reflected, why = _hwm_reflects_cache(latest or {}, races)
                out["cache_reflect"] = why
                if not reflected:
                    out["ok"] = False
                    out["error"] = "hwm_publish_predicted_at_stale"
                    notes.append(f"hwm_stale:{why}")
        except Exception as e:
            out["latest_check_error"] = f"{type(e).__name__}: {e}"
        out["n_races_cache"] = len(races)
        out["schedule_date"] = day
        out["export_errors"] = errors
        out["notes"] = notes
        out["attempts"] = attempts
        if out.get("ok"):
            notes.append(str(_upload_diag(out)))
            return out
        # attempts を含めない浅いコピー（循環参照防止）
        attempts.append({k: v for k, v in out.items() if k != "attempts"})
        errors.append(str(out.get("error") or "hwm_failed"))
        notes.append(str(_upload_diag({k: v for k, v in out.items() if k != "attempts"})))
    except Exception as e:
        errors.append(f"hwm: {type(e).__name__}: {e}")
        attempts.append({"ok": False, "error": errors[-1]})

    # 4) 正式ヘルパ再公開（Edge day_rows / morning holmes map）
    try:
        from official_republish_from_cache import run as official_run

        out = official_run()
        attempts.append(dict(out) if isinstance(out, dict) else {"raw": str(out)})
        if isinstance(out, dict) and out.get("ok") and int(out.get("race_count") or 0) > 0:
            q = out.get("quality") or {}
            out["n_races_cache"] = len(races)
            out["notes"] = notes + list(out.get("notes") or [])
            out["attempts"] = attempts
            out["export_errors"] = errors
            notes.append(str(_upload_diag(out)))
            if q.get("ok_quality") or int(out.get("race_count") or 0) > 0:
                return out
        errors.append(str((out or {}).get("error") if isinstance(out, dict) else "official_failed"))
    except Exception as e:
        errors.append(f"official: {type(e).__name__}: {e}")
        attempts.append({"ok": False, "error": errors[-1]})

    # 5) 自前構築（会場殻問題の最終手段・品質補正込み）
    try:
        from standalone_publish_from_cache import run as standalone_run

        out = standalone_run()
        attempts.append(dict(out) if isinstance(out, dict) else {"raw": str(out)})
        if isinstance(out, dict) and out.get("ok") and int(out.get("race_count") or 0) > 0:
            out["n_races_cache"] = len(races)
            out["notes"] = notes + list(out.get("notes") or [])
            out["attempts"] = attempts
            out["export_errors"] = errors
            notes.append(str(_upload_diag(out)))
            return out
        errors.append(str((out or {}).get("error") if isinstance(out, dict) else "standalone_failed"))
    except Exception as e:
        errors.append(f"standalone: {type(e).__name__}: {e}")
        attempts.append({"ok": False, "error": errors[-1]})

    out = {
        "ok": False,
        "error": "all_publish_paths_failed",
        "errors": errors,
        "schedule_date": day,
        "n_races_cache": len(races),
        "notes": notes,
        "attempts": attempts,
        "traceback": traceback.format_exc()[-2000:],
    }
    notes.append(str(_upload_diag(out)))
    return out


def main() -> int:
    out = run_publish(force=True)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

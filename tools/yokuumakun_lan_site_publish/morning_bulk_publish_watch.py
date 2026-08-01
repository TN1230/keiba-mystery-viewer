#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""閲覧サイト latest.json の公開遅れを拾って強制 publish する常駐向けスクリプト。

用途:
1. 朝一斉完了なのに latest が空/前日 → publish
2. 直前予想成功でキャッシュの predicted_at が公開より新しい → publish
3. 直前窓のレースが朝予想のまま（他レースの直近 publish に隠れない）→ publish

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
# 発走約15分前更新が取りこぼされたとき、窓内レースを保険 publish。
# 他レースの直近 updated_at ではスキップしない（本日の主因）。
_PRE_RACE_LOOKAHEAD = timedelta(minutes=30)
_PRE_RACE_LOOKBACK = timedelta(minutes=15)
_PRE_RACE_FRESH_BEFORE = timedelta(minutes=20)


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
    """文字列日時に加え、キャッシュの Unix 秒(float/int)も解釈する。"""
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
            # ミリ秒誤検出を避ける（2001〜2286年相当の秒）
            if 1_000_000_000 <= ts < 10_000_000_000:
                return datetime.fromtimestamp(ts, tz=_JST)
        except Exception:
            return None
    s = str(value).strip()
    if not s:
        return None
    # "1785547781.997" のような数値文字列
    try:
        ts = float(s)
        if 1_000_000_000 <= ts < 10_000_000_000:
            return datetime.fromtimestamp(ts, tz=_JST)
    except Exception:
        pass
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


def _predicted_at_of(rinfo: dict[str, Any]) -> Any:
    """キャッシュ／公開レースから predicted_at を取り出す。"""
    if rinfo.get("predicted_at") not in (None, ""):
        return rinfo.get("predicted_at")
    pred = rinfo.get("prediction")
    if isinstance(pred, dict) and pred.get("predicted_at") not in (None, ""):
        return pred.get("predicted_at")
    meta = rinfo.get("meta")
    if isinstance(meta, dict) and meta.get("predicted_at") not in (None, ""):
        return meta.get("predicted_at")
    return None


def _iter_public_races(snap: dict[str, Any]) -> list[dict[str, Any]]:
    races: list[dict[str, Any]] = []
    for v in snap.get("venues") or []:
        if isinstance(v, dict):
            for r in v.get("races") or []:
                if isinstance(r, dict):
                    races.append(r)
    return races


def _load_cache_races(root: Path, day: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for fp in _cache_paths(root, day):
        try:
            with fp.open("rb") as f:
                races = pickle.load(f)
        except Exception:
            continue
        if not isinstance(races, dict):
            continue
        for rid, rinfo in races.items():
            if isinstance(rinfo, dict):
                out[str(rid)] = rinfo
    return out


def _max_predicted_at_from_public(snap: dict[str, Any]) -> datetime | None:
    best: datetime | None = None
    for r in _iter_public_races(snap):
        dt = _parse_dt(_predicted_at_of(r))
        if dt and (best is None or dt > best):
            best = dt
    return best


def _max_predicted_at_from_cache(root: Path, day: str) -> datetime | None:
    best: datetime | None = None
    for rinfo in _load_cache_races(root, day).values():
        dt = _parse_dt(_predicted_at_of(rinfo))
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
    """キャッシュの predicted_at が公開より新しければ再 publish。

    max 比較に加え、同一 race_id でキャッシュが新しいケースも拾う
    （別レースの max が同じでも取りこぼしを防ぐ）。
    """
    cache_races = _load_cache_races(root, day)
    if not cache_races:
        return False, "no_cache_predicted_at"

    cache_max = _max_predicted_at_from_cache(root, day)
    pub_max = _max_predicted_at_from_public(snap)
    if cache_max is not None and (
        pub_max is None or cache_max > pub_max + timedelta(seconds=30)
    ):
        return True, f"cache_pred={cache_max.isoformat()} public_pred={pub_max}"

    pub_by_id = {
        str(r.get("race_id") or ""): r
        for r in _iter_public_races(snap)
        if r.get("race_id")
    }
    newer_ids: list[str] = []
    for rid, rinfo in cache_races.items():
        c_dt = _parse_dt(_predicted_at_of(rinfo))
        if c_dt is None:
            continue
        pub = pub_by_id.get(rid)
        if pub is None:
            continue
        p_dt = _parse_dt(_predicted_at_of(pub))
        if p_dt is None or c_dt > p_dt + timedelta(seconds=30):
            newer_ids.append(rid)
            if len(newer_ids) >= 3:
                break
    if newer_ids:
        return True, f"per_race_cache_newer={','.join(newer_ids)}"
    return False, "cache_not_newer"


def _public_stale_during_prerace_window(snap: dict[str, Any]) -> tuple[bool, str]:
    """直前窓のレースが朝予想のままなら再 publish。

    重要: 他レースの直近 updated_at ではスキップしない。
    本日(2026-08-01)は札幌11R公開(15:11)のあと、新潟7R/中京7R が
    朝の predicted_at のまま残った。
    """
    now = datetime.now(_JST)
    updated = _parse_dt(snap.get("updated_at"))

    window_start = now - _PRE_RACE_LOOKBACK
    window_end = now + _PRE_RACE_LOOKAHEAD
    stale_in_window = 0
    examples: list[str] = []
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
        pred = _parse_dt(_predicted_at_of(r))
        # 発走20分以上前の predicted_at のまま = 直前成功が未反映
        if pred is None or (start_dt - pred) > _PRE_RACE_FRESH_BEFORE:
            stale_in_window += 1
            place = str(r.get("place") or "")
            rn = str(r.get("R") or r.get("race_no") or "")
            examples.append(f"{place}{rn}R@{start_s}")
    if stale_in_window > 0:
        detail = (
            f"stale_prerace_races={stale_in_window}"
            f" examples={','.join(examples[:4])}"
            f" updated_at={updated.isoformat() if updated else None}"
        )
        return True, detail
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


def _ensure_permanent_hooks(root: Path) -> dict[str, Any]:
    """指示なしで翌日以降も動くよう、パッチ欠落・timer 停止を自己修復する。"""
    info: dict[str, Any] = {"patched_pre_race": False, "timer_ok": None}
    worker = root / "pre_race_auto_predict_worker.py"
    patcher = root / "patch_pre_race_publish_on_success.py"
    try:
        if worker.is_file():
            text = worker.read_text(encoding="utf-8", errors="replace")
            if "BEGIN pre_race_publish_on_success" not in text and patcher.is_file():
                import subprocess

                cp = subprocess.run(
                    [sys.executable, str(patcher), str(root)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                info["patched_pre_race"] = cp.returncode == 0
                info["patch_rc"] = cp.returncode
                info["patch_out"] = ((cp.stdout or "") + (cp.stderr or ""))[-300:]
            else:
                info["patched_pre_race"] = "BEGIN pre_race_publish_on_success" in text
    except Exception as e:
        info["patch_error"] = f"{type(e).__name__}: {e}"

    try:
        import subprocess

        cp = subprocess.run(
            ["systemctl", "is-enabled", "yokuum-morning-publish-watch.timer"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        enabled = (cp.stdout or "").strip() == "enabled"
        info["timer_ok"] = enabled
        if not enabled:
            installer = root / "install_daily_publish_watch.py"
            if installer.is_file():
                cp2 = subprocess.run(
                    [sys.executable, str(installer), str(root)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                info["timer_reinstall_rc"] = cp2.returncode
                info["timer_reinstall_out"] = ((cp2.stdout or "") + (cp2.stderr or ""))[-400:]
    except Exception as e:
        info["timer_error"] = f"{type(e).__name__}: {e}"
    return info


def main() -> int:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    ensure = _ensure_permanent_hooks(root)
    day = _today()
    snap = _fetch_public()
    out = decide_publish(root, day, snap)
    out["ensure"] = ensure

    if out.get("action") != "force_publish":
        print(json.dumps(out, ensure_ascii=False, default=str))
        return 0

    from force_publish_public_snapshot import run_publish

    result = run_publish(force=True)
    out["result"] = result
    # hwm が偽成功しても standalone まで落ちるよう force_publish 側で不合格化済み
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

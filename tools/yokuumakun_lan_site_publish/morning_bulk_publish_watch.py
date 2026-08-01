#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""閲覧サイト latest.json の公開遅れを拾って強制 publish する常駐向けスクリプト。

用途:
1. 朝一斉完了なのに latest が空/前日 → publish
2. 直前予想成功でキャッシュの predicted_at が公開より新しい → publish
3. 直前窓のレースが朝予想のまま（他レースの直近 publish に隠れない）→ publish
4. publish 失敗で立った pending フラグ → 即 publish（購入時間確保）

systemd timer（開催帯 30 秒）または viewer_publish_wake の oneshot から呼ぶ。
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


def _public_stale_during_prerace_window(
    snap: dict[str, Any], root: Path | None = None, day: str | None = None
) -> tuple[bool, str]:
    """直前窓で「キャッシュは直前更新済みなのに公開が朝のまま」なら再 publish。

    未予想（キャッシュも朝のまま）のレースでは無駄に publish しない。
    """
    now = datetime.now(_JST)
    updated = _parse_dt(snap.get("updated_at"))
    cache_by_id: dict[str, dict[str, Any]] = {}
    if root is not None and day:
        cache_by_id = _load_cache_races(root, day)

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
        pub_pred = _parse_dt(_predicted_at_of(r))
        pub_stale = pub_pred is None or (start_dt - pub_pred) > _PRE_RACE_FRESH_BEFORE
        if not pub_stale:
            continue
        rid = str(r.get("race_id") or "")
        cache_r = cache_by_id.get(rid) if rid else None
        cache_pred = _parse_dt(_predicted_at_of(cache_r)) if cache_r else None
        # キャッシュ側が直前更新済み（発走20分以内）なのに公開だけ古い
        cache_fresh = cache_pred is not None and (start_dt - cache_pred) <= _PRE_RACE_FRESH_BEFORE
        cache_newer = (
            cache_pred is not None
            and (pub_pred is None or cache_pred > pub_pred + timedelta(seconds=30))
        )
        if not (cache_fresh or cache_newer):
            continue
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


def _load_pending(root: Path) -> dict[str, Any] | None:
    try:
        from viewer_publish_wake import load_pending

        return load_pending(root)
    except Exception:
        fp = root / "logs" / "viewer_publish_pending.json"
        if not fp.is_file():
            return None
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None


def _clear_pending(root: Path) -> None:
    try:
        from viewer_publish_wake import clear_pending

        clear_pending(root)
        return
    except Exception:
        pass
    try:
        fp = root / "logs" / "viewer_publish_pending.json"
        if fp.is_file():
            fp.unlink()
    except Exception:
        pass


def _minutes_to_nearest_post(snap: dict[str, Any] | None) -> float | None:
    """公開 snapshot 上、いまから最も近い発走までの分。"""
    if not snap:
        return None
    now = datetime.now(_JST)
    best: float | None = None
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
        mins = (start_dt - now).total_seconds() / 60.0
        # 発走直後〜これから 40 分以内を購入時間帯として見る
        if -5 <= mins <= 40:
            if best is None or abs(mins) < abs(best):
                best = mins
    return best


def decide_publish(root: Path, day: str, snap: dict[str, Any] | None) -> dict[str, Any]:
    """テスト用: publish 要否を判定する。"""
    out: dict[str, Any] = {"day": day, "action": "noop"}
    pending = _load_pending(root)
    if pending:
        out["action"] = "force_publish"
        out["reason"] = "pending_wake"
        out["detail"] = (
            f"pending_reason={pending.get('reason')} "
            f"race_id={pending.get('race_id')} at={pending.get('at')}"
        )
        out["pending"] = pending
        return out

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

    stale, why2 = _public_stale_during_prerace_window(snap, root, day)
    if stale:
        out["action"] = "force_publish"
        out["reason"] = "stale_during_prerace"
        out["detail"] = why2
        return out

    out["reason"] = "already_fresh"
    out["detail"] = why
    return out


# 直前予想済みなのに閲覧サイトが止まっている = 運用異常
_ANOMALY_REASONS = {
    "cache_newer_than_public": "viewer_publish_lag_after_predict",
    "stale_during_prerace": "viewer_publish_lag_in_prerace_window",
    "empty_or_wrong_day": "viewer_snapshot_empty_or_wrong_day",
    "pending_wake": "viewer_publish_pending_wake",
}
_ANOMALY_STATE_NAME = "viewer_publish_anomaly_state.json"
_ANOMALY_LOG_NAME = "viewer_publish_anomaly.log"
_ANOMALY_NOTIFY_COOLDOWN = timedelta(minutes=15)


def classify_anomaly(
    decision: dict[str, Any], snap: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """decide_publish 結果から「異常」を明示分類する。"""
    if decision.get("action") != "force_publish":
        return None
    reason = str(decision.get("reason") or "")
    kind = _ANOMALY_REASONS.get(reason)
    if not kind:
        return None
    titles = {
        "viewer_publish_lag_after_predict": (
            "【異常】直前予想はキャッシュ更新済みだが、閲覧サイト latest.json が止まっています"
        ),
        "viewer_publish_lag_in_prerace_window": (
            "【異常】直前窓のレースで公開 predicted_at が古いままです（キャッシュは新しい）"
        ),
        "viewer_snapshot_empty_or_wrong_day": (
            "【異常】閲覧サイト snapshot が空、または開催日不一致です"
        ),
        "viewer_publish_pending_wake": (
            "【異常】公開 publish が失敗したため pending 経由で直ちに再試行します"
        ),
    }
    title = titles.get(kind, "【異常】閲覧サイト公開の取りこぼし")
    near = _minutes_to_nearest_post(snap)
    urgent_purchase = near is not None and -5 <= near <= 25
    if urgent_purchase:
        title = (
            f"【異常・発走間近】馬券購入時間確保のため直ちに公開修復します"
            f"（最寄り発走まで約{near:.0f}分）\n"
            + title
        )
    return {
        "anomaly": True,
        "kind": kind,
        "reason": reason,
        "title": title,
        "detail": decision.get("detail") or reason,
        "day": decision.get("day"),
        "minutes_to_nearest_post": near,
        "urgent_purchase_window": urgent_purchase,
    }


def _anomaly_paths(root: Path) -> tuple[Path, Path]:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / _ANOMALY_STATE_NAME, logs / _ANOMALY_LOG_NAME


def _load_anomaly_state(root: Path) -> dict[str, Any]:
    state_path, _ = _anomaly_paths(root)
    if not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_anomaly_state(root: Path, state: dict[str, Any]) -> None:
    state_path, _ = _anomaly_paths(root)
    try:
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


def _append_anomaly_log(root: Path, line: str) -> None:
    _, log_path = _anomaly_paths(root)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(_JST).isoformat(timespec='seconds')}] {line}\n")
    except Exception:
        pass


def _should_notify_anomaly(root: Path, kind: str) -> bool:
    """同一 kind の連打通知を cooldown で抑止する。"""
    state = _load_anomaly_state(root)
    key = f"last_notify_{kind}"
    last = _parse_dt(state.get(key))
    now = datetime.now(_JST)
    if last is not None and now - last < _ANOMALY_NOTIFY_COOLDOWN:
        return False
    state[key] = now.isoformat(timespec="seconds")
    state["last_kind"] = kind
    _save_anomaly_state(root, state)
    return True


def _discord_notify(root: Path, content: str) -> dict[str, Any]:
    """エラー系統 Discord に異常を通知。hwm ヘルパがあればそれを使う。"""
    text = (content or "")[:1900]
    # 1) hwm 経路
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import hwm  # type: ignore

        url = ""
        if hasattr(hwm, "_discord_error_webhook_url"):
            url = str(hwm._discord_error_webhook_url() or "").strip()
        if url and hasattr(hwm, "_discord_send_webhook"):
            ok, msg = hwm._discord_send_webhook(url, text)
            return {"ok": bool(ok), "via": "hwm", "message": str(msg)[:200]}
    except Exception as e:
        hwm_err = f"{type(e).__name__}: {e}"
    else:
        hwm_err = "hwm_webhook_unavailable"

    # 2) .env 直接
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
    except Exception:
        pass
    url = ""
    for key in (
        "DISCORD_WEBHOOK_ERROR",
        "DISCORD_WEBHOOK_URL_3",
        "DISCORD_WEBHOOK_FAILURE",
        "DISCORD_WEBHOOK_TEST_ALWAYS",
    ):
        url = (os.environ.get(key) or "").strip().strip('"')
        if url:
            break
    if not url:
        return {"ok": False, "via": "none", "message": hwm_err}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"content": text}, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            _ = resp.read()
            return {"ok": 200 <= resp.status < 300, "via": "env", "status": resp.status}
    except Exception as e:
        return {"ok": False, "via": "env", "message": f"{type(e).__name__}: {e}"}


def _upload_anomaly_status(root: Path, payload: dict[str, Any]) -> str | None:
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        url, err = upload_json_object("ops/viewer_publish_anomaly_last.json", payload)
        if err:
            return f"upload_err={err}"
        return f"upload_ok={url}"
    except Exception as e:
        return f"upload_exc={type(e).__name__}:{e}"


def _verify_resolved(root: Path, day: str, *, ignore_pending: bool = True) -> dict[str, Any]:
    """修復後の確認。pending は「修復試行のトリガ」なので検証時は無視する。"""
    pending_backup = None
    pending_fp = root / "logs" / "viewer_publish_pending.json"
    if ignore_pending and pending_fp.is_file():
        try:
            pending_backup = pending_fp.read_text(encoding="utf-8")
            pending_fp.unlink()
        except Exception:
            pending_backup = None
    try:
        snap = _fetch_public()
        decision = decide_publish(root, day, snap)
        still = classify_anomaly(decision, snap)
        return {
            "resolved": still is None,
            "decision": {
                "action": decision.get("action"),
                "reason": decision.get("reason"),
                "detail": decision.get("detail"),
            },
            "anomaly_after": still,
        }
    finally:
        if pending_backup is not None:
            try:
                pending_fp.write_text(pending_backup, encoding="utf-8")
            except Exception:
                pass


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

    anomaly = classify_anomaly(out, snap)
    if anomaly is None:
        # 正常時は古い pending を掃除
        _clear_pending(root)
        print(json.dumps(out, ensure_ascii=False, default=str))
        return 0

    # --- 異常検知: 気付いて直ちに対応（購入時間を食わない） ---
    out["anomaly"] = anomaly
    _append_anomaly_log(
        root,
        f"DETECT kind={anomaly['kind']} reason={anomaly['reason']} "
        f"urgent={anomaly.get('urgent_purchase_window')} "
        f"eta_min={anomaly.get('minutes_to_nearest_post')} "
        f"detail={anomaly.get('detail')}",
    )

    notify_info: dict[str, Any] = {"skipped": True}
    # 発走間近は cooldown を bypass して必ず知らせる
    force_notify = bool(anomaly.get("urgent_purchase_window"))
    if force_notify or _should_notify_anomaly(root, str(anomaly["kind"])):
        if force_notify:
            # cooldown キーも更新しておく
            _should_notify_anomaly(root, str(anomaly["kind"]))
        msg = (
            f"{anomaly['title']}\n"
            f"day={day}\n"
            f"reason={anomaly['reason']}\n"
            f"detail={anomaly.get('detail')}\n"
            f"→ 直ちに force publish で異変解消します（馬券購入時間確保）"
        )
        notify_info = _discord_notify(root, msg)
        notify_info["skipped"] = False
        notify_info["forced"] = force_notify
        _append_anomaly_log(root, f"NOTIFY {notify_info}")
    out["notify"] = notify_info

    from force_publish_public_snapshot import run_publish

    def _slim_result(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            slim = {
                k: result.get(k)
                for k in (
                    "ok",
                    "via",
                    "error",
                    "race_count",
                    "schedule_date",
                    "cache_reflect",
                    "n_races_cache",
                )
                if k in result
            }
            errs = result.get("export_errors") or result.get("errors")
            if errs:
                slim["errors"] = list(errs)[:8]
            return slim
        return {"raw": str(result)[:500]}

    result = run_publish(force=True)
    out["result"] = _slim_result(result)

    verify = _verify_resolved(root, day)
    # 1回で解消しない場合、購入時間帯は間を置かず再試行
    if not verify.get("resolved"):
        _append_anomaly_log(root, "RETRY immediate second force_publish")
        result2 = run_publish(force=True)
        out["result_retry"] = _slim_result(result2)
        verify = _verify_resolved(root, day)
        if isinstance(result2, dict) and result2.get("ok"):
            result = result2
            out["result"] = out["result_retry"]

    out["verify"] = {
        "resolved": verify.get("resolved"),
        "decision": verify.get("decision"),
    }
    _append_anomaly_log(
        root,
        f"REMEDIATE ok={bool(isinstance(result, dict) and result.get('ok'))} "
        f"resolved={verify.get('resolved')} via={(out.get('result') or {}).get('via')}",
    )

    # 修復失敗は必ず通知（cooldown 無視）
    if not verify.get("resolved"):
        fail_msg = (
            "【異常・未解消】閲覧サイト自動更新の修復に失敗しました（購入時間に影響し得ます）\n"
            f"day={day}\n"
            f"detect={anomaly['kind']}\n"
            f"publish={out.get('result')}\n"
            f"after={verify.get('decision')}"
        )
        out["notify_failed"] = _discord_notify(root, fail_msg)
        _append_anomaly_log(root, f"NOTIFY_FAIL {out['notify_failed']}")
    else:
        _clear_pending(root)
        # 復旧も一度知らせる（同 kind の cooldown 内ならスキップ）
        if _should_notify_anomaly(root, f"recovered:{anomaly['kind']}"):
            ok_msg = (
                "【復旧】閲覧サイトの公開遅れを直ちに自動修復しました\n"
                f"day={day}\n"
                f"was={anomaly['kind']}\n"
                f"via={(out.get('result') or {}).get('via')}"
            )
            out["notify_recovered"] = _discord_notify(root, ok_msg)
            _append_anomaly_log(root, f"NOTIFY_RECOVERED {out['notify_recovered']}")

    status_payload = {
        "updated_at": datetime.now(_JST).isoformat(timespec="seconds"),
        "day": day,
        "anomaly": anomaly,
        "notify": out.get("notify"),
        "result": out.get("result"),
        "verify": out.get("verify"),
        "ensure": ensure,
    }
    out["status_upload"] = _upload_anomaly_status(root, status_payload)

    print(json.dumps(out, ensure_ascii=False, default=str))
    ok = bool(isinstance(result, dict) and result.get("ok") and verify.get("resolved"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

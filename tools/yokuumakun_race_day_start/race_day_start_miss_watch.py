#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""05:15 JST miss-guard: if race day and automation inactive, start it.

Also posts a Discord failure webhook when recovery is needed / fails.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    return Path("/opt/yokuumakun_auto-x")


def _load_env(root: Path) -> None:
    envf = root / ".env"
    if not envf.is_file():
        return
    try:
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def _service() -> str:
    return (
        os.environ.get("YOKUMAKUN_SERVER_AUTO_SERVICE")
        or "yokuum-server-automation-x.service"
    ).strip()


def _is_active(unit: str) -> bool:
    try:
        cp = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (cp.stdout or "").strip() == "active"
    except Exception:
        return False


def _sudo_run(cmd: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    pw = (
        os.environ.get("YOKUMAKUN_SUDO_PASS")
        or os.environ.get("YOKUMAKUN_SSH_PASS")
        or ""
    ).strip()
    if pw:
        return subprocess.run(
            ["sudo", "-S", "-p", ""] + cmd,
            input=pw + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return subprocess.run(
        ["sudo", "-n"] + cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _likely_race_day(root: Path) -> tuple[bool, str]:
    day = datetime.now(_JST).strftime("%Y-%m-%d")
    ymd = day.replace("-", "")
    logs = root / "logs"
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        if (logs / name).is_file():
            return True, f"cache:{name}"
    # schedule helper
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from hwm_server_standalone import _today_is_scheduled_race_day  # type: ignore

        if bool(_today_is_scheduled_race_day()):
            return True, "helper:_today_is_scheduled_race_day"
    except Exception:
        pass
    # weekend heuristic (JRA often Sat/Sun); miss-guard is cheap to run
    if datetime.now(_JST).weekday() >= 5:  # 5=Sat 6=Sun
        return True, "weekend_heuristic"
    # if start cron/timer exists and preflight ran today, treat as race-day candidate
    pf = logs / "cron_race_day_preflight.log"
    if pf.is_file():
        try:
            mt = datetime.fromtimestamp(pf.stat().st_mtime, _JST).strftime("%Y-%m-%d")
            if mt == day and pf.stat().st_size > 0:
                return True, "preflight_log_today"
        except Exception:
            pass
    return False, "not_race_day_candidate"


def _error_webhook() -> str:
    for k in (
        "DISCORD_WEBHOOK_FAILURE",
        "DISCORD_WEBHOOK_URL_3",
        "DISCORD_WEBHOOK_ERROR",
        "ADMIN_FAILURE_WEBHOOK_URL",
    ):
        v = (os.environ.get(k) or "").strip()
        if v.startswith("http"):
            return v
    return ""


def _post_webhook(url: str, content: str, embeds: list[dict[str, Any]] | None = None) -> None:
    payload: dict[str, Any] = {"content": content[:1800]}
    if embeds:
        payload["embeds"] = embeds[:3]
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except Exception as e:
        print(f"WARN: webhook failed: {type(e).__name__}: {e}", flush=True)


def main() -> int:
    root = _root()
    _load_env(root)
    os.environ.setdefault("TZ", "Asia/Tokyo")
    unit = _service()
    now = datetime.now(_JST)
    log = root / "logs" / "race_day_start_miss_watch.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    def w(msg: str) -> None:
        line = f"{now.isoformat(timespec='seconds')} {msg}"
        print(line, flush=True)
        try:
            with log.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    race, why = _likely_race_day(root)
    w(f"likely_race_day={race} reason={why} unit={unit}")
    if not race:
        w("skip: not a race-day candidate")
        return 0

    if _is_active(unit):
        w("ok: automation already active")
        return 0

    w("MISS: automation inactive after 05:00 window — recovering")
    wrapper = root / "server_deployment" / "race_day_start_wrapper.sh"
    start = root / "server_deployment" / "race_day_start_hwm.sh"
    if not start.is_file():
        start = root / "race_day_start_hwm.sh"

    notes: list[str] = []
    if wrapper.is_file():
        cp = subprocess.run(
            ["bash", str(wrapper)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "YOKUMAKUN_ROOT": str(root), "TZ": "Asia/Tokyo"},
        )
        notes.append(f"wrapper rc={cp.returncode}")
    elif start.is_file():
        cp = subprocess.run(
            ["bash", str(start)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "YOKUMAKUN_ROOT": str(root), "TZ": "Asia/Tokyo"},
        )
        notes.append(f"start_script rc={cp.returncode}")
    else:
        notes.append("no_start_script")

    if not _is_active(unit):
        cp = _sudo_run(["systemctl", "start", unit])
        notes.append(f"systemctl_start rc={cp.returncode}")

    active = _is_active(unit)
    w(f"after_recover active={active} notes={';'.join(notes)}")

    wh = _error_webhook()
    if wh:
        color = 0x2ECC71 if active else 0xE74C3C
        _post_webhook(
            wh,
            content="【開催日 05:15】automation 起動ミス監視",
            embeds=[
                {
                    "title": "race_day_start miss-guard",
                    "description": (
                        f"reason={why}\n"
                        f"recovered_active={active}\n"
                        f"notes={'; '.join(notes)}\n"
                        f"time={now.isoformat(timespec='seconds')}"
                    )[:1800],
                    "color": color,
                }
            ],
        )
    return 0 if active else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開遅れを即時解消するための pending フラグ + watch 起こし。

pre_race / morning_bulk の publish 失敗時に呼び、systemd oneshot を起動する。
馬券購入時間が食われないよう、2分待ちに頼らず直ちに安全網を動かす。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
PENDING_NAME = "viewer_publish_pending.json"
WATCH_SERVICE = "yokuum-morning-publish-watch.service"


def _root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    if (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def pending_path(root: Path | None = None) -> Path:
    r = _root(root)
    logs = r / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / PENDING_NAME


def load_pending(root: Path | None = None) -> dict[str, Any] | None:
    fp = pending_path(root)
    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def clear_pending(root: Path | None = None) -> None:
    fp = pending_path(root)
    try:
        if fp.is_file():
            fp.unlink()
    except Exception:
        pass


def write_pending(
    *,
    reason: str,
    race_id: str = "",
    error: str = "",
    root: Path | None = None,
) -> Path:
    r = _root(root)
    fp = pending_path(r)
    payload = {
        "at": datetime.now(_JST).isoformat(timespec="seconds"),
        "reason": str(reason or "publish_failed")[:200],
        "race_id": str(race_id or "")[:32],
        "error": str(error or "")[:400],
        "urgent": True,
    }
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fp


def wake_publish_watch() -> dict[str, Any]:
    """timer 待ちせず oneshot service を即起動。"""
    try:
        cp = subprocess.run(
            ["systemctl", "start", WATCH_SERVICE],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "ok": cp.returncode == 0,
            "rc": cp.returncode,
            "out": ((cp.stdout or "") + (cp.stderr or "")).strip()[-300:],
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def mark_pending_and_wake(
    *,
    reason: str = "publish_failed",
    race_id: str = "",
    error: str = "",
    root: Path | None = None,
) -> dict[str, Any]:
    """pending を書いて watch を起こす（購入時間確保用の即時経路）。"""
    r = _root(root)
    fp = write_pending(reason=reason, race_id=race_id, error=error, root=r)
    wake = wake_publish_watch()
    return {"pending": str(fp), "wake": wake}


if __name__ == "__main__":
    # 手動: python viewer_publish_wake.py [reason]
    reason = sys.argv[1] if len(sys.argv) > 1 else "manual"
    print(json.dumps(mark_pending_and_wake(reason=reason), ensure_ascii=False))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""毎日 05:00 / 05:15 JST の race-day start (+ miss-guard) systemd timer を恒久インストール。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _sudo_run(cmd: list[str], *, timeout: float = 90.0) -> subprocess.CompletedProcess[str]:
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


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    here = Path(__file__).resolve().parent
    unit_dir = root / "server_deployment"
    unit_dir.mkdir(parents=True, exist_ok=True)

    # copy wrapper + miss watch into server_deployment
    for name in (
        "race_day_start_wrapper.sh",
        "race_day_start_miss_watch.py",
        "yokuum-race-day-start.service.example",
        "yokuum-race-day-start.timer.example",
        "yokuum-race-day-start-guard.service.example",
        "yokuum-race-day-start-guard.timer.example",
    ):
        src = here / name
        if not src.is_file():
            print(f"ERROR: missing {src}", file=sys.stderr)
            return 1
        dst = unit_dir / name
        shutil.copy2(src, dst)
        if name.endswith(".sh"):
            try:
                dst.chmod(dst.stat().st_mode | 0o111)
            except Exception:
                pass
        print(f"installed {dst}")

    # ensure original start script exists (server-owned)
    start = unit_dir / "race_day_start_hwm.sh"
    if not start.is_file():
        alt = root / "race_day_start_hwm.sh"
        if alt.is_file():
            shutil.copy2(alt, start)
            print(f"copied start script -> {start}")
        else:
            print(
                f"WARN: {start} missing — wrapper will fall back to systemctl start only",
                file=sys.stderr,
            )

    installs = [
        (
            unit_dir / "yokuum-race-day-start.service.example",
            "/etc/systemd/system/yokuum-race-day-start.service",
        ),
        (
            unit_dir / "yokuum-race-day-start.timer.example",
            "/etc/systemd/system/yokuum-race-day-start.timer",
        ),
        (
            unit_dir / "yokuum-race-day-start-guard.service.example",
            "/etc/systemd/system/yokuum-race-day-start-guard.service",
        ),
        (
            unit_dir / "yokuum-race-day-start-guard.timer.example",
            "/etc/systemd/system/yokuum-race-day-start-guard.timer",
        ),
    ]
    for src, dst in installs:
        cp = _sudo_run(["cp", str(src), dst])
        print(f"cp {src.name} -> {dst} rc={cp.returncode}")
        if cp.returncode != 0:
            print((cp.stderr or "")[-400:], file=sys.stderr)
            return cp.returncode

    for cmd in (
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "yokuum-race-day-start.timer"],
        ["systemctl", "enable", "--now", "yokuum-race-day-start-guard.timer"],
    ):
        cp = _sudo_run(cmd)
        print(" ".join(cmd), "rc=", cp.returncode)
        if cp.returncode != 0:
            print((cp.stderr or "")[-400:], file=sys.stderr)
            return cp.returncode

    for cmd in (
        ["systemctl", "is-enabled", "yokuum-race-day-start.timer"],
        ["systemctl", "is-enabled", "yokuum-race-day-start-guard.timer"],
        ["systemctl", "list-timers", "yokuum-race-day-start*", "--no-pager"],
    ):
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(" ".join(cmd), "->", (cp.stdout or cp.stderr or "").strip()[:400])

    print("DONE: race-day start timers enabled (05:00 + 05:15 Asia/Tokyo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

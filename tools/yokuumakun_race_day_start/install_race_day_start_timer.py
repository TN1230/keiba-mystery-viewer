#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""毎日 05:00 / 05:15 JST の race-day start (+ miss-guard) systemd timer を恒久インストール。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_PLACEHOLDERS = frozenset(
    {
        "",
        "…",
        "...",
        "....",
        "YOUR_PASSWORD",
        "your_password",
        "changeme",
        "password",
    }
)


def _is_placeholder(pw: str) -> bool:
    s = (pw or "").strip()
    if s in _PLACEHOLDERS:
        return True
    if "←" in s:
        return True
    return False


def _load_env_file(path: Path, *, override_placeholders: bool = True) -> None:
    if not path.is_file():
        return
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if not k:
                continue
            cur = os.environ.get(k)
            if cur is None:
                os.environ[k] = v
            elif override_placeholders and _is_placeholder(cur) and not _is_placeholder(v):
                os.environ[k] = v
    except Exception:
        pass


def _sudo_password() -> str:
    for key in ("YOKUMAKUN_SUDO_PASS", "YOKUMAKUN_SSH_PASS", "SUDO_PASSWORD"):
        pw = (os.environ.get(key) or "").strip()
        if pw and not _is_placeholder(pw):
            return pw
    return ""


def _sudo_run(cmd: list[str], *, timeout: float = 90.0) -> subprocess.CompletedProcess[str]:
    pw = _sudo_password()
    if pw:
        # -n first if cached; else -S once (avoid sudo retry eating empty stdin)
        cached = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if cached.returncode == 0:
            return subprocess.run(
                ["sudo", "-n"] + cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        return subprocess.run(
            ["sudo", "-S", "-p", ""] + cmd,
            input=pw + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "SUDO_PROMPT": ""},
        )
    return subprocess.run(
        ["sudo", "-n"] + cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    _load_env_file(root / ".env")
    _load_env_file(root / "server_deployment" / "hwm_runtime.env")

    here = Path(__file__).resolve().parent
    unit_dir = root / "server_deployment"
    unit_dir.mkdir(parents=True, exist_ok=True)

    pw = _sudo_password()
    if not pw:
        print(
            "ERROR: no usable YOKUMAKUN_SUDO_PASS "
            "(unset, or still a docs placeholder like '…'). "
            f"Set a real sudo password in the environment or {root}/.env",
            file=sys.stderr,
        )
        return 2

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
        # bootstrap が先に server_deployment へ置いたあと、本スクリプトも
        # 同ディレクトリから実行されると src==dst になる
        try:
            same = src.resolve() == dst.resolve()
        except OSError:
            same = False
        if same:
            print(f"already in place {dst}")
        else:
            try:
                shutil.copy2(src, dst)
                print(f"installed {dst}")
            except shutil.SameFileError:
                print(f"already in place {dst}")
        if name.endswith(".sh"):
            try:
                dst.chmod(dst.stat().st_mode | 0o111)
            except Exception:
                pass

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
            err = (cp.stderr or cp.stdout or "").strip()
            print(err[-400:], file=sys.stderr)
            if "Authentication" in err or cp.returncode == 1:
                print(
                    "ERROR: sudo rejected YOKUMAKUN_SUDO_PASS. "
                    "Export the real password for this host user, "
                    f"or fix {root}/.env (replace any '…' placeholder).",
                    file=sys.stderr,
                )
            return cp.returncode or 1

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

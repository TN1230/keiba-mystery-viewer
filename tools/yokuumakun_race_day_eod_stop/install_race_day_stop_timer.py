#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""毎日 20:00 JST に race_day_stop を動かす systemd timer を恒久インストールする。"""

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


def _load_env_file(path: Path) -> None:
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
            elif _is_placeholder(cur) and not _is_placeholder(v):
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

    if not _sudo_password():
        print(
            "ERROR: no usable YOKUMAKUN_SUDO_PASS "
            "(unset, or still a docs placeholder like '…'). "
            f"Set a real sudo password in the environment or {root}/.env",
            file=sys.stderr,
        )
        return 2

    stop = unit_dir / "race_day_stop_hwm.sh"
    if not stop.is_file():
        alt = root / "race_day_stop_hwm.sh"
        if alt.is_file():
            shutil.copy2(alt, stop)
            print(f"copied stop script -> {stop}")
        else:
            print(f"ERROR: missing {stop}", file=sys.stderr)
            return 1
    try:
        stop.chmod(stop.stat().st_mode | 0o111)
    except Exception:
        pass

    for name in (
        "yokuum-race-day-stop.service.example",
        "yokuum-race-day-stop.timer.example",
    ):
        src = here / name
        if not src.is_file():
            print(f"ERROR: missing {src}", file=sys.stderr)
            return 1
        dst = unit_dir / name
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

    # 実 unit は example をそのまま /etc へ（パスは auto-x 固定）
    svc_src = unit_dir / "yokuum-race-day-stop.service.example"
    tmr_src = unit_dir / "yokuum-race-day-stop.timer.example"
    cmds = [
        ["cp", str(svc_src), "/etc/systemd/system/yokuum-race-day-stop.service"],
        ["cp", str(tmr_src), "/etc/systemd/system/yokuum-race-day-stop.timer"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "yokuum-race-day-stop.timer"],
    ]
    for cmd in cmds:
        cp = _sudo_run(cmd)
        print(" ".join(cmd), "rc=", cp.returncode)
        if cp.stdout:
            print(cp.stdout[-400:])
        if cp.stderr and cp.returncode != 0:
            print(cp.stderr[-400:], file=sys.stderr)
        if cp.returncode != 0:
            err = (cp.stderr or cp.stdout or "")
            if "Authentication" in err:
                print(
                    "ERROR: sudo rejected YOKUMAKUN_SUDO_PASS. "
                    f"Fix export or {root}/.env (replace any '…' placeholder).",
                    file=sys.stderr,
                )
            return cp.returncode

    # 確認表示
    for cmd in (
        ["systemctl", "is-enabled", "yokuum-race-day-stop.timer"],
        ["systemctl", "list-timers", "yokuum-race-day-stop.timer", "--no-pager"],
    ):
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(" ".join(cmd), "->", (cp.stdout or cp.stderr or "").strip()[:300])

    print("DONE: yokuum-race-day-stop.timer enabled (daily 20:00 Asia/Tokyo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

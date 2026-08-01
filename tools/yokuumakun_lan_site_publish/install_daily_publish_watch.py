#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""明日以降も自動で latest.json を埋める systemd timer を入れる。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    here = Path(__file__).resolve().parent
    for name in (
        "morning_bulk_publish_watch.py",
        "force_publish_public_snapshot.py",
        "patch_pre_race_publish_on_success.py",
        "viewer_publish_wake.py",
        "race_course_distance.py",
        "race_pace_label.py",
    ):
        src = here / name
        dst = root / name
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
            print(f"installed {dst}")
        elif src.is_file():
            print(f"already in place {dst}")

    # 直前成功パスへ publish を恒久注入（ファイルがあるときだけ）
    pre_race = root / "pre_race_auto_predict_worker.py"
    patcher = root / "patch_pre_race_publish_on_success.py"
    if pre_race.is_file() and patcher.is_file():
        cp = subprocess.run(
            [sys.executable, str(patcher), str(root)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        print("patch_pre_race", "rc=", cp.returncode)
        if cp.stdout:
            print(cp.stdout[-400:])
        if cp.stderr and cp.returncode != 0:
            print(cp.stderr[-400:], file=sys.stderr)

    unit_dir = root / "server_deployment"
    unit_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "yokuum-morning-publish-watch.service.example",
        "yokuum-morning-publish-watch.timer.example",
    ):
        src = here / name
        if src.is_file():
            shutil.copy2(src, unit_dir / name)
            print(f"installed {unit_dir / name}")

    svc_src = unit_dir / "yokuum-morning-publish-watch.service.example"
    tmr_src = unit_dir / "yokuum-morning-publish-watch.timer.example"
    if not svc_src.is_file() or not tmr_src.is_file():
        print("WARN: unit examples missing", file=sys.stderr)
        return 1

    cmds = [
        ["cp", str(svc_src), "/etc/systemd/system/yokuum-morning-publish-watch.service"],
        ["cp", str(tmr_src), "/etc/systemd/system/yokuum-morning-publish-watch.timer"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "yokuum-morning-publish-watch.timer"],
        ["systemctl", "start", "yokuum-morning-publish-watch.service"],
    ]
    for cmd in cmds:
        # sudo -S if YOKUMAKUN_SUDO_PASS set
        import os

        pw = (os.environ.get("YOKUMAKUN_SUDO_PASS") or os.environ.get("YOKUMAKUN_SSH_PASS") or "").strip()
        if pw:
            full = ["sudo", "-S", "-p", ""] + cmd
            cp = subprocess.run(full, input=pw + "\n", text=True, capture_output=True, timeout=60)
        else:
            cp = subprocess.run(["sudo"] + cmd, capture_output=True, text=True, timeout=60)
        print(" ".join(cmd), "rc=", cp.returncode)
        if cp.stdout:
            print(cp.stdout[-400:])
        if cp.stderr and cp.returncode != 0:
            print(cp.stderr[-400:], file=sys.stderr)
        if cp.returncode != 0:
            return cp.returncode
    print("DONE: daily publish watch timer enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAN ops 入口: 開催日タイムテーブル deploy を委譲（Cloud Agent 不使用）。"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

RESULT_FILE = Path(__file__).with_name("_deploy_lan_ops_out.txt")


def main() -> int:
    target = (
        Path(__file__).resolve().parent.parent
        / "yokuumakun_race_day_timetable"
        / "deploy_paramiko.py"
    )
    if not target.is_file():
        msg = f"RESULT: FAILED\nmissing {target}"
        print(msg)
        RESULT_FILE.write_text(msg + "\n", encoding="utf-8")
        return 1

    # Run timetable deploy in-process so stdout/RESULT stay familiar
    sys.argv = [str(target)]
    try:
        runpy.run_path(str(target), run_name="__main__")
    except SystemExit as e:
        code = int(e.code or 0) if isinstance(e.code, int) or e.code is None else 1
    else:
        code = 0

    # Mirror timetable result file if present
    src = target.with_name("_deploy_race_day_timetable_out.txt")
    if src.is_file():
        text = src.read_text(encoding="utf-8", errors="replace")
        RESULT_FILE.write_text(text, encoding="utf-8")
        if "RESULT: SUCCESS" in text:
            print("LAN_OPS: timetable deploy SUCCESS (see _deploy_lan_ops_out.txt)")
        else:
            print("LAN_OPS: timetable deploy finished with issues (see _deploy_lan_ops_out.txt)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

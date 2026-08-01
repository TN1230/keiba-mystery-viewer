#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwm_server_automation.py の _tick に JST 20:00 以降の自己停止ガードを注入する。

背景:
  hwm / server-automation 自体は 20:00 に終了しない。停止は本来 cron の
  race_day_stop_hwm.sh が担う。cron/sudo 失敗時の保険として、JST 20:00 以降は
  _tick が SystemExit してプロセスを終える。

使い方:
  python3 patch_automation_jst_eod_guard.py /opt/yokuumakun_auto-x
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN jst_eod_stop_guard"
END = "# END jst_eod_stop_guard"

GUARD_BLOCK = """\
    {begin}
    # 開催日 20:00 JST 以降は tick を打ち切りプロセス終了（cron stop の保険）
    try:
        from datetime import datetime as _dt_eod
        from zoneinfo import ZoneInfo as _ZI_eod
        _now_eod = _dt_eod.now(_ZI_eod("Asia/Tokyo"))
        if int(_now_eod.hour) >= 20:
            try:
                _dbg_morning_bulk_log(
                    "EOD",
                    "hwm_server_automation.py:_tick",
                    "jst_eod_stop_guard_exit",
                    {{"jst": _now_eod.isoformat(timespec="seconds")}},
                )
            except Exception:
                pass
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    {end}
"""


def _inject_block() -> str:
    return GUARD_BLOCK.format(begin=BEGIN, end=END)


def already_patched(text: str) -> bool:
    return BEGIN in text and END in text


def patch_text(text: str) -> tuple[str, str]:
    """Returns (new_text, status). status: already|patched|error:..."""
    if already_patched(text):
        return text, "already"
    # Insert right after `_tick` body starts / mode-enabled early return if present
    anchor_candidates = [
        '    if not _hwm_server_auto_mode_enabled():\n        return\n',
        "    if not _hwm_server_auto_mode_enabled():\n        return\n",
        "def _tick() -> None:\n",
    ]
    block = _inject_block()
    for anchor in anchor_candidates:
        if anchor in text:
            if anchor.startswith("def _tick"):
                # after function def line, skip into body: find first indented line after def
                idx = text.find(anchor)
                if idx < 0:
                    continue
                insert_at = idx + len(anchor)
                new = text[:insert_at] + block + text[insert_at:]
                return new, "patched"
            new = text.replace(anchor, anchor + block, 1)
            return new, "patched"
    return text, "error:anchor_not_found"


def patch(root: Path) -> dict:
    target = root / "hwm_server_automation.py"
    if not target.is_file():
        return {"ok": False, "error": f"missing {target}"}
    original = target.read_text(encoding="utf-8", errors="replace")
    new, status = patch_text(original)
    if status.startswith("error"):
        return {"ok": False, "error": status, "path": str(target)}
    if status == "already":
        return {"ok": True, "status": status, "path": str(target)}
    bak = target.with_suffix(target.suffix + ".bak_jst_eod")
    if not bak.is_file():
        shutil.copy2(target, bak)
    target.write_text(new, encoding="utf-8")
    return {"ok": True, "status": status, "path": str(target), "backup": str(bak)}


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    out = patch(root)
    print(out)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

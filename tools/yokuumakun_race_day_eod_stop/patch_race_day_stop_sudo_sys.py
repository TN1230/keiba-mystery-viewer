#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""race_day_stop_hwm.sh の bare `sudo systemctl` を非対話対応に差し替える。

cron から動かすとき `sudo` がパスワード要求で失敗し、automation が止まらない
事例への対策。YOKUMAKUN_SUDO_PASS / SUDO_PASSWORD があれば sudo -S を使う。
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN sudo_sys_race_day_stop"
END = "# END sudo_sys_race_day_stop"

SUDO_SYS_FN = r'''
{begin}
sudo_sys() {
  # non-interactive sudo for cron
  local pw="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-${SUDO_PASSWORD:-}}}"
  if [[ -n "$pw" ]]; then
    echo "$pw" | sudo -S -p '' "$@"
  else
    sudo -n "$@"
  fi
}
{end}
'''.replace("{begin}", BEGIN).replace("{end}", END)


def patch_text(text: str) -> tuple[str, str]:
    if BEGIN in text and "sudo_sys systemctl" in text:
        return text, "already"

    new = text
    if BEGIN not in new:
        # insert after set -euo pipefail or after export TZ
        m = re.search(r"(?m)^export TZ=Asia/Tokyo\s*$", new)
        if m:
            insert_at = m.end()
            new = new[:insert_at] + "\n" + SUDO_SYS_FN + new[insert_at:]
        else:
            m2 = re.search(r"(?m)^set -euo pipefail\s*$", new)
            if not m2:
                return text, "error:no_insert_point"
            insert_at = m2.end()
            new = new[:insert_at] + "\n" + SUDO_SYS_FN + new[insert_at:]

    # replace bare sudo systemctl stop/restart with sudo_sys
    new2, n = re.subn(
        r"(?m)^(\s*)sudo systemctl (stop|restart|start) ",
        r"\1sudo_sys systemctl \2 ",
        new,
    )
    if n == 0 and "sudo_sys systemctl" not in new2:
        return text, "error:no_sudo_systemctl_lines"
    return new2, "patched" if n or BEGIN not in text else "already"


def patch(root: Path) -> dict:
    candidates = [
        root / "server_deployment" / "race_day_stop_hwm.sh",
        root / "race_day_stop_hwm.sh",
    ]
    target = next((p for p in candidates if p.is_file()), None)
    if target is None:
        return {"ok": False, "error": "race_day_stop_hwm.sh not found"}
    original = target.read_text(encoding="utf-8", errors="replace")
    new, status = patch_text(original)
    if status.startswith("error"):
        return {"ok": False, "error": status, "path": str(target)}
    if status == "already":
        return {"ok": True, "status": status, "path": str(target)}
    bak = target.with_suffix(target.suffix + ".bak_sudo_sys")
    if not bak.is_file():
        shutil.copy2(target, bak)
    target.write_text(new, encoding="utf-8")
    try:
        target.chmod(target.stat().st_mode | 0o111)
    except Exception:
        pass
    return {"ok": True, "status": status, "path": str(target), "backup": str(bak)}


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    out = patch(root)
    print(out)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

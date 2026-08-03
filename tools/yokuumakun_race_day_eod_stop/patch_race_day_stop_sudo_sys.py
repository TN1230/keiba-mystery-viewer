#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""race_day_stop_hwm.sh を cron/systemd 非対話実行向けに硬化する。

- bare `sudo systemctl` → sudo_sys（YOKUMAKUN_SUDO_PASS / sudo -n）
- ROOT/.env と hwm_runtime.env を自動 load（次回以降パスワードを cron に書かなくてよい）
- TZ=Asia/Tokyo を保証
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN_SUDO = "# BEGIN sudo_sys_race_day_stop"
END_SUDO = "# END sudo_sys_race_day_stop"
BEGIN_ENV = "# BEGIN load_env_race_day_stop"
END_ENV = "# END load_env_race_day_stop"
BEGIN_CLEAR = "# BEGIN clear_latest_after_stop"
END_CLEAR = "# END clear_latest_after_stop"

CLEAR_LATEST_BLOCK = f"""
{BEGIN_CLEAR}
# publish-watch 埋め戻し対策: latest を cleared 表示へ（失敗しても stop 自体は成功扱い）
CLEAR_PY="${{ROOT}}/clear_latest_public_snapshot.py"
if [[ -f "$CLEAR_PY" ]]; then
  PYBIN="${{ROOT}}/.venv/bin/python"
  [[ -x "$PYBIN" ]] || PYBIN="$(command -v python3 || true)"
  if [[ -n "$PYBIN" ]]; then
    log "INFO: clear_latest_public_snapshot.py を実行します"
    set +e
    (cd "$ROOT" && "$PYBIN" -u "$CLEAR_PY") >>"$LOG_FILE" 2>&1
    clear_rc=$?
    set -e
    log "INFO: clear_latest rc=${{clear_rc}}"
  fi
fi
{END_CLEAR}
"""

SUDO_SYS_FN = f"""
{BEGIN_SUDO}
sudo_sys() {{
  # non-interactive sudo for cron / systemd timer
  local pw="${{YOKUMAKUN_SUDO_PASS:-${{YOKUMAKUN_SSH_PASS:-${{SUDO_PASSWORD:-}}}}}}"
  if [[ -n "$pw" ]]; then
    echo "$pw" | sudo -S -p '' "$@"
  else
    sudo -n "$@"
  fi
}}
{END_SUDO}
"""

LOAD_ENV_BLOCK = f"""
{BEGIN_ENV}
# cron/timer からでも .env の sudo パス等を読む
_load_env_file() {{
  local f="$1"
  [[ -f "$f" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  . "$f"
  set +a
}}
_load_env_file "${{ROOT}}/.env"
_load_env_file "${{ROOT}}/server_deployment/hwm_runtime.env"
{END_ENV}
"""


def patch_text(text: str) -> tuple[str, str]:
    new = text
    changed = False

    if "export TZ=Asia/Tokyo" not in new:
        m = re.search(r"(?m)^set -euo pipefail\s*$", new)
        if m:
            new = new[: m.end()] + "\n\nexport TZ=Asia/Tokyo\n" + new[m.end() :]
            changed = True
        else:
            new = "export TZ=Asia/Tokyo\n" + new
            changed = True

    if BEGIN_SUDO not in new:
        m = re.search(r"(?m)^export TZ=Asia/Tokyo\s*$", new)
        if not m:
            return text, "error:no_tz_line"
        new = new[: m.end()] + "\n" + SUDO_SYS_FN + new[m.end() :]
        changed = True

    # ROOT 定義の直後に env load
    if BEGIN_ENV not in new:
        m = re.search(
            r"(?m)^ROOT=\"\$\{YOKUMAKUN_ROOT:-\$\(cd \"\$\(dirname \"\$0\"\)/\.\.\" && pwd\)\}\"\s*$",
            new,
        )
        if not m:
            m = re.search(r"(?m)^ROOT=.*$", new)
        if not m:
            return text, "error:no_root_line"
        new = new[: m.end()] + "\n" + LOAD_ENV_BLOCK + new[m.end() :]
        changed = True

    new2, n = re.subn(
        r"(?m)^(\s*)sudo systemctl (stop|restart|start) ",
        r"\1sudo_sys systemctl \2 ",
        new,
    )
    if n:
        changed = True
        new = new2
    elif "sudo_sys systemctl" not in new:
        return text, "error:no_sudo_systemctl_lines"

    if BEGIN_CLEAR not in new:
        # DONE 行の直前、または末尾に clear を挿入
        m = re.search(r"(?m)^log \"DONE race_day_stop_hwm\"\s*$", new)
        if m:
            new = new[: m.start()] + CLEAR_LATEST_BLOCK + "\n" + new[m.start() :]
            changed = True
        else:
            new = new.rstrip() + "\n" + CLEAR_LATEST_BLOCK + "\n"
            changed = True

    if (
        not changed
        and BEGIN_SUDO in text
        and BEGIN_ENV in text
        and BEGIN_CLEAR in text
        and "sudo_sys systemctl" in text
    ):
        return text, "already"
    return new, "patched" if changed else "already"


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
    # 片方しか無い場合は server_deployment にも揃える
    sd = root / "server_deployment" / "race_day_stop_hwm.sh"
    if target.resolve() != sd.resolve() and target.is_file():
        sd.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, sd)
    return {"ok": True, "status": status, "path": str(target), "backup": str(bak)}


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    out = patch(root)
    print(out)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

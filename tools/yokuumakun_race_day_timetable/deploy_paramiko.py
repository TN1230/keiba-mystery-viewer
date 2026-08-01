#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows LAN から自宅サーバーへ開催日タイムテーブルを一括適用する。

先週まで成功していた deploy_*_paramiko.py と同じ方式:
  - 接続先: 192.168.128.178 / tn
  - パスワード: Desktop\\ローカルサーバーIP.txt の pass: または YOKUMAKUN_SSH_PASS
  - パックを SFTP で上げ、サーバー上で apply_uploaded_packs.sh を実行
  - GitHub raw curl は使わない（CDN キャッシュ問題を回避）

クラウド VM からは LAN IP に届かないことが多い。自宅 Windows から実行する。
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required: pip install paramiko") from None

REMOTE_ROOT = "/opt/yokuumakun_auto-x"
REMOTE_TMP = "/tmp/race_day_timetable_deploy"
HERE = Path(__file__).resolve().parent
REPO_TOOLS = HERE.parent
RESULT_FILE = HERE / "_deploy_race_day_timetable_out.txt"

UPLOAD_MAP: list[tuple[Path, str]] = [
    (HERE / "apply_uploaded_packs.sh", "apply_uploaded_packs.sh"),
    # start
    (REPO_TOOLS / "yokuumakun_race_day_start" / "race_day_start_wrapper.sh", "start/race_day_start_wrapper.sh"),
    (REPO_TOOLS / "yokuumakun_race_day_start" / "race_day_start_miss_watch.py", "start/race_day_start_miss_watch.py"),
    (REPO_TOOLS / "yokuumakun_race_day_start" / "ensure_race_day_start_cron.sh", "start/ensure_race_day_start_cron.sh"),
    (REPO_TOOLS / "yokuumakun_race_day_start" / "install_race_day_start_timer.py", "start/install_race_day_start_timer.py"),
    (
        REPO_TOOLS / "yokuumakun_race_day_start" / "yokuum-race-day-start.service.example",
        "start/yokuum-race-day-start.service.example",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_start" / "yokuum-race-day-start.timer.example",
        "start/yokuum-race-day-start.timer.example",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_start" / "yokuum-race-day-start-guard.service.example",
        "start/yokuum-race-day-start-guard.service.example",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_start" / "yokuum-race-day-start-guard.timer.example",
        "start/yokuum-race-day-start-guard.timer.example",
    ),
    # eod
    (
        REPO_TOOLS / "yokuumakun_race_day_eod_stop" / "patch_automation_jst_eod_guard.py",
        "eod/patch_automation_jst_eod_guard.py",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_eod_stop" / "patch_race_day_stop_sudo_sys.py",
        "eod/patch_race_day_stop_sudo_sys.py",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_eod_stop" / "ensure_race_day_stop_cron.sh",
        "eod/ensure_race_day_stop_cron.sh",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_eod_stop" / "install_race_day_stop_timer.py",
        "eod/install_race_day_stop_timer.py",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_eod_stop" / "yokuum-race-day-stop.service.example",
        "eod/yokuum-race-day-stop.service.example",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_eod_stop" / "yokuum-race-day-stop.timer.example",
        "eod/yokuum-race-day-stop.timer.example",
    ),
    # evening
    (
        REPO_TOOLS / "yokuumakun_race_day_evening_functional_test" / "race_day_evening_functional_test.py",
        "evening/race_day_evening_functional_test.py",
    ),
    (
        REPO_TOOLS / "yokuumakun_race_day_evening_functional_test" / "install_crontab.sh",
        "evening/install_crontab.sh",
    ),
    # publish
    (
        REPO_TOOLS / "yokuumakun_lan_site_publish" / "morning_bulk_publish_watch.py",
        "publish/morning_bulk_publish_watch.py",
    ),
    (
        REPO_TOOLS / "yokuumakun_lan_site_publish" / "clear_latest_public_snapshot.py",
        "publish/clear_latest_public_snapshot.py",
    ),
]


def _password() -> str:
    env = (
        os.environ.get("YOKUMAKUN_SSH_PASS")
        or os.environ.get("YOKUU_SSH_PASS")
        or os.environ.get("SSHPASS")
        or ""
    ).strip()
    if env and env not in {"…", "..."}:
        return env
    for cand in (
        os.environ.get("YOKUMAKUN_SSH_CREDS", ""),
        r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt",
        r"C:\Users\user\Desktop\ローカルサーバーIP.txt",
        str(Path.home() / "Desktop" / "ローカルサーバーIP.txt"),
    ):
        if not cand:
            continue
        p = Path(cand)
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"(?im)^pass:\s*(\S+)\s*$", text) or re.search(
            r"(?im)^password:\s*(\S+)\s*$", text
        )
        if m:
            return m.group(1).strip()
    raise RuntimeError("password not found in YOKUMAKUN_SSH_PASS or ローカルサーバーIP.txt")


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def _sftp_mkdirs(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except OSError:
            try:
                sftp.mkdir(cur)
            except OSError:
                pass


def main() -> int:
    host = (
        os.environ.get("YOKUMAKUN_SSH_HOST")
        or os.environ.get("YOKUU_SSH_HOST")
        or "192.168.128.178"
    )
    user = (
        os.environ.get("YOKUMAKUN_SSH_USER")
        or os.environ.get("YOKUU_SSH_USER")
        or "tn"
    )
    pw = _password()
    lines: list[str] = []

    def log(msg: str) -> None:
        safe = msg.replace(pw, "***")
        lines.append(safe)
        print(safe, flush=True)

    missing = [str(src) for src, _ in UPLOAD_MAP if not src.is_file()]
    if missing:
        log("RESULT: FAILED\nmissing local files:\n- " + "\n- ".join(missing))
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        log(f"connect {user}@{host} …")
        client.connect(
            host,
            username=user,
            password=pw,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=30,
            auth_timeout=30,
        )
        sftp = client.open_sftp()
        _sftp_mkdirs(sftp, REMOTE_TMP)
        for sub in ("start", "eod", "evening", "publish"):
            _sftp_mkdirs(sftp, f"{REMOTE_TMP}/{sub}")

        for local, rel in UPLOAD_MAP:
            remote = f"{REMOTE_TMP}/{rel}"
            sftp.put(str(local), remote)
            log(f"uploaded {rel}")
        sftp.close()

        cmd = " && ".join(
            [
                f"chmod +x {shlex.quote(REMOTE_TMP + '/apply_uploaded_packs.sh')}",
                f"export YOKUMAKUN_ROOT={shlex.quote(REMOTE_ROOT)}",
                f"export YOKUMAKUN_SUDO_PASS={shlex.quote(pw)}",
                f"export YOKUMAKUN_SSH_PASS={shlex.quote(pw)}",
                f"bash {shlex.quote(REMOTE_TMP + '/apply_uploaded_packs.sh')} "
                f"{shlex.quote(REMOTE_TMP)}",
            ]
        )
        log("remote apply_uploaded_packs …")
        rc, out = _run(client, cmd, timeout=600)
        log(out[-6000:] if out else "(no output)")
        log(f"remote_rc={rc}")

        # verify timers / cron
        vrc, vout = _run(
            client,
            "systemctl list-timers 'yokuum-race-day-*' --no-pager; "
            "echo '----'; crontab -l 2>/dev/null | grep -nE 'CRON_TZ|race_day_|evening_functional' || true",
            timeout=60,
        )
        log(vout)
        log(f"verify_rc={vrc}")
        client.close()

        if rc == 0:
            log("RESULT: SUCCESS")
        else:
            log("RESULT: FAILED (remote apply non-zero)")
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0 if rc == 0 else 1
    except Exception as e:
        log(f"RESULT: FAILED\n{type(e).__name__}: {e}")
        if "Connection reset" in str(e) or "timed out" in str(e).lower():
            log(
                "HINT: this PC cannot reach the LAN SSH port. "
                "Run deploy_from_windows.ps1 on the home Windows PC that is on the same LAN."
            )
        RESULT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

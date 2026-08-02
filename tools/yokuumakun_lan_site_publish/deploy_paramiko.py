#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows LAN から自宅サーバーへ接続し、閲覧サイト latest.json を強制公開する。

先週まで成功していた deploy_*_paramiko.py と同じ方式:
  - 接続先: 192.168.128.178 / tn
  - パスワード: Desktop\\ローカルサーバーIP.txt の pass:
  - sudo: echo pass | sudo -S（必要な箇所のみ）

クラウドや bore トンネルは不要。
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
LOCAL_DIR = Path(__file__).resolve().parent
RESULT_FILE = Path(__file__).with_name("_deploy_lan_site_publish_out.txt")


def _password() -> str:
    env = (os.environ.get("YOKUMAKUN_SSH_PASS") or os.environ.get("YOKUU_SSH_PASS") or "").strip()
    if env:
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


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 300) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def _sudo(pw: str, cmd: str) -> str:
    return f"echo {shlex.quote(pw)} | sudo -S -p '' {cmd}"


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST", "192.168.128.178")
    user = os.environ.get("YOKUMAKUN_SSH_USER", "tn")
    pw = _password()
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg, flush=True)

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
        remote_tmp = "/tmp/lan_site_publish"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        for name in (
            "force_publish_public_snapshot.py",
            "standalone_publish_from_cache.py",
            "official_republish_from_cache.py",
            "patch_worker_publish_on_success.py",
            "patch_pre_race_publish_on_success.py",
            "viewer_publish_wake.py",
            "race_course_distance.py",
            "race_pace_label.py",
            "install_publish_endpoint.py",
            "morning_bulk_publish_watch.py",
            "install_daily_publish_watch.py",
            "yokuum-morning-publish-watch.service.example",
            "yokuum-morning-publish-watch.timer.example",
        ):
            local = LOCAL_DIR / name
            if local.is_file():
                sftp.put(str(local), f"{remote_tmp}/{name}")
                log(f"uploaded {name}")
        sftp.close()

        # 1) パッチ適用 + 即 publish + 当日午後までの timer
        cmd = " && ".join(
            [
                f"export YOKUMAKUN_SUDO_PASS={shlex.quote(pw)}",
                f"python3 {remote_tmp}/patch_worker_publish_on_success.py {REMOTE_ROOT}",
                f"python3 {remote_tmp}/patch_pre_race_publish_on_success.py {REMOTE_ROOT}",
                f"python3 {remote_tmp}/install_publish_endpoint.py {REMOTE_ROOT}",
                f"cp {remote_tmp}/force_publish_public_snapshot.py "
                f"{remote_tmp}/morning_bulk_publish_watch.py "
                f"{remote_tmp}/viewer_publish_wake.py "
                f"{remote_tmp}/race_course_distance.py "
                f"{remote_tmp}/race_pace_label.py "
                f"{remote_tmp}/standalone_publish_from_cache.py "
                f"{remote_tmp}/official_republish_from_cache.py {REMOTE_ROOT}/",
                f"mkdir -p {REMOTE_ROOT}/server_deployment && "
                f"cp {remote_tmp}/yokuum-morning-publish-watch.*.example "
                f"{REMOTE_ROOT}/server_deployment/",
                f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile "
                "force_publish_public_snapshot.py morning_bulk_publish_watch.py "
                "viewer_publish_wake.py race_course_distance.py race_pace_label.py "
                "morning_bulk_server_worker.py pre_race_auto_predict_worker.py "
                "admin_panel_api.py",
                f"cd {REMOTE_ROOT} && .venv/bin/python force_publish_public_snapshot.py",
                f"python3 {remote_tmp}/install_daily_publish_watch.py {REMOTE_ROOT}",
                _sudo(pw, "systemctl restart yokuum-admin-panel.service") + " || true",
                "sleep 1",
                "curl -sS http://127.0.0.1:8791/health || true",
                "curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
                "public-viewer/snapshots/latest.json | head -c 500",
            ]
        )
        rc, out = _run(client, cmd, timeout=420)
        log(out.replace(pw, "***"))
        log(f"remote rc={rc}")
        client.close()

        # 公開確認（このPCから）
        import urllib.request

        with urllib.request.urlopen(
            "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
            "public-viewer/snapshots/latest.json",
            timeout=30,
        ) as resp:
            body = resp.read().decode()
        log("latest.json: " + body[:500])
        if '"cleared": true' in body or '"race_count": 0' in body:
            log("RESULT: FAILED (still cleared or race_count=0)")
            rc = 1
        elif '"schedule_date": "2026-08-01"' in body or '"race_count":' in body:
            # date may roll; accept race_count>0
            import json as _json

            snap = _json.loads(body)
            if int(snap.get("race_count") or 0) > 0 and not snap.get("cleared"):
                log("RESULT: SUCCESS")
                rc = 0
            else:
                log("RESULT: FAILED (unexpected snapshot)")
                rc = 1
        else:
            log("RESULT: FAILED")
            rc = 1
    except Exception as e:
        log(f"RESULT: FAILED\n{type(e).__name__}: {e}")
        rc = 1

    RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

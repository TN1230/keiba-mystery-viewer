#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows LAN から race_progression_sim を auto-x へコピーし GET /tenkai を有効化する。"""

from __future__ import annotations

import os
import re
import shlex
import sys
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise SystemExit("paramiko required: pip install paramiko") from None

REMOTE_ROOT = os.environ.get("YOKUU_ROOT", "/opt/yokuumakun_auto-x")
LOCAL_DIR = Path(__file__).resolve().parent
RESULT_FILE = Path(__file__).with_name("_deploy_tenkai_sim_out.txt")

LOCAL_SOURCE_CANDIDATES = [
    Path(os.environ["YOKUMAKUN_SIM_SOURCE"]) if os.environ.get("YOKUMAKUN_SIM_SOURCE") else None,
    Path(r"C:\Users\mocco\Desktop\yokuumakun"),
    Path.home() / "Desktop" / "yokuumakun",
]


def _password() -> str:
    env = (
        os.environ.get("YOKUMAKUN_SSH_PASS")
        or os.environ.get("YOKUU_SSH_PASS")
        or ""
    ).strip()
    if env:
        return env
    for cand in (
        os.environ.get("YOKUMAKUN_SSH_CREDS", ""),
        r"C:\Users\mocco\Desktop\ローカルサーバーIP.txt",
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
    raise RuntimeError("password not found")


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 300) -> tuple[int, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
    return stdout.channel.recv_exit_status(), out


def _sudo(pw: str, cmd: str) -> str:
    return f"echo {shlex.quote(pw)} | sudo -S -p '' {cmd}"


def _local_source() -> Path:
    for c in LOCAL_SOURCE_CANDIDATES:
        if c and (c / "race_progression_sim.py").is_file():
            return c
    raise RuntimeError(
        "ローカルに race_progression_sim.py がありません。"
        " YOKUMAKUN_SIM_SOURCE か Desktop\\yokuumakun を確認してください。"
    )


def _sftp_put_dir(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    try:
        sftp.mkdir(remote)
    except OSError:
        pass
    for root, dirs, files in os.walk(local):
        rel = os.path.relpath(root, local).replace("\\", "/")
        rdir = remote if rel == "." else f"{remote}/{rel}"
        try:
            sftp.mkdir(rdir)
        except OSError:
            pass
        for d in dirs:
            try:
                sftp.mkdir(f"{rdir}/{d}")
            except OSError:
                pass
        for f in files:
            sftp.put(str(Path(root) / f), f"{rdir}/{f}")


def main() -> int:
    host = os.environ.get("YOKUMAKUN_SSH_HOST") or os.environ.get("YOKUU_SSH_HOST") or "192.168.128.178"
    user = os.environ.get("YOKUMAKUN_SSH_USER") or os.environ.get("YOKUU_SSH_USER") or "tn"
    pw = _password()
    src = _local_source()
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)
        print(msg, flush=True)

    try:
        from copy_sim_from_yokuumakun import collect_files

        files = collect_files(src)
    except Exception:
        files = [src / "race_progression_sim.py"]

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
    try:
        sftp = client.open_sftp()
        remote_tmp = "/tmp/tenkai_sim_launch"
        try:
            sftp.mkdir(remote_tmp)
        except OSError:
            pass
        for name in (
            "copy_sim_from_yokuumakun.py",
            "tenkai_sim_gateway.py",
            "install_tenkai_endpoint.py",
            "publish_tenkai_discovery.py",
            "bootstrap_on_server.sh",
        ):
            sftp.put(str(LOCAL_DIR / name), f"{remote_tmp}/{name}")
            log(f"uploaded tool {name}")

        remote_src = f"{remote_tmp}/yokuumakun_src"
        try:
            sftp.mkdir(remote_src)
        except OSError:
            pass
        for item in files:
            rel = item.relative_to(src).as_posix()
            if item.is_dir():
                _sftp_put_dir(sftp, item, f"{remote_src}/{rel}")
                log(f"uploaded dir {rel}")
            else:
                parent = str(Path(rel).parent).replace("\\", "/")
                if parent and parent != ".":
                    # ensure nested dirs
                    acc = remote_src
                    for part in parent.split("/"):
                        acc = f"{acc}/{part}"
                        try:
                            sftp.mkdir(acc)
                        except OSError:
                            pass
                sftp.put(str(item), f"{remote_src}/{rel}")
                log(f"uploaded {rel}")
        sftp.close()

        cmds = [
            f"mkdir -p {REMOTE_ROOT}/_tenkai_sim_install",
            f"cp {remote_tmp}/copy_sim_from_yokuumakun.py {REMOTE_ROOT}/_tenkai_sim_install/",
            f"cp {remote_tmp}/tenkai_sim_gateway.py {REMOTE_ROOT}/_tenkai_sim_install/",
            f"cp {remote_tmp}/install_tenkai_endpoint.py {REMOTE_ROOT}/_tenkai_sim_install/",
            f"cp {remote_tmp}/publish_tenkai_discovery.py {REMOTE_ROOT}/_tenkai_sim_install/",
            (
                f"cd {REMOTE_ROOT}/_tenkai_sim_install && "
                f"python3 copy_sim_from_yokuumakun.py --source {remote_src} --dest {REMOTE_ROOT} --force"
            ),
            (
                f"cd {REMOTE_ROOT}/_tenkai_sim_install && "
                f"python3 install_tenkai_endpoint.py {REMOTE_ROOT}"
            ),
            (
                f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile "
                "admin_panel_api.py tenkai_sim_gateway.py && echo COMPILE_OK"
            ),
            _sudo(pw, "systemctl restart yokuum-admin-panel.service"),
            "sleep 1",
            "systemctl is-active yokuum-admin-panel.service",
            "curl -sS -o /tmp/tenkai_probe.html -w '%{http_code}' "
            "'http://127.0.0.1:8791/tenkai?race_id=probe' || true",
            "echo",
            "head -c 240 /tmp/tenkai_probe.html || true",
            "echo",
            (
                f"cd {REMOTE_ROOT}/_tenkai_sim_install && YOKUMAKUN_ROOT={REMOTE_ROOT} "
                f"{REMOTE_ROOT}/.venv/bin/python publish_tenkai_discovery.py"
            ),
            "curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/admin_api.json | head -c 500",
            "echo",
            "echo DONE_TENKAI_SIM",
        ]

        rc, out = _run(client, " && ".join(cmds), timeout=600)
        log(out.replace(pw, "***"))
        if rc != 0:
            log(f"ERROR remote rc={rc}")
            RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
            return 1
        if "DONE_TENKAI_SIM" not in out:
            log("ERROR: DONE marker missing")
            RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
            return 1
        log("OK")
        RESULT_FILE.write_text("\n".join(lines), encoding="utf-8")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        msg = f"FATAL: {type(e).__name__}: {e}"
        print(msg, file=sys.stderr)
        RESULT_FILE.write_text(msg + "\n", encoding="utf-8")
        raise SystemExit(1)

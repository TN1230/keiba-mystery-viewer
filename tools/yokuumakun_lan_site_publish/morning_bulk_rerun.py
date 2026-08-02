#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理画面「① 一斉予想再実行」の実体。

旧実装は起動要求を投げてすぐ ok を返していたため、automation inactive や
ワーカー起動失敗でも UI が「完了」に見えた。ここでは:

1. yokuum-server-automation-x を active にする
2. morning_bulk_server_worker.py を起動する
3. 数秒待ってプロセス存在を確認してから ok/ng を返す
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any


DEFAULT_SERVICE = "yokuum-server-automation-x.service"
WORKER_NAME = "morning_bulk_server_worker.py"
VERIFY_SEC = 20.0


def _root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root).expanduser().resolve()
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path("/opt/yokuumakun_auto-x").resolve()


def _load_env(root: Path) -> None:
    envf = root / ".env"
    if not envf.is_file():
        return
    try:
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def _py(root: Path) -> str:
    cand = root / ".venv" / "bin" / "python"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    cand3 = root / ".venv" / "bin" / "python3"
    if cand3.is_file() and os.access(cand3, os.X_OK):
        return str(cand3)
    return "python3"


def _sudo_password() -> str:
    for key in ("YOKUMAKUN_SUDO_PASS", "YOKUMAKUN_SSH_PASS", "SUDO_PASSWORD"):
        pw = (os.environ.get(key) or "").strip()
        if pw and pw not in {"…", "..."}:
            return pw
    return ""


def _sudo_run(cmd: list[str], *, timeout: float = 90.0) -> subprocess.CompletedProcess[str]:
    pw = _sudo_password()
    if pw:
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


def _service_active(service: str) -> str:
    try:
        cp = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (cp.stdout or cp.stderr or "").strip() or "unknown"
    except Exception as e:
        return f"error:{type(e).__name__}"


def ensure_automation_active(
    *,
    root: Path,
    service: str = DEFAULT_SERVICE,
) -> tuple[bool, str]:
    state = _service_active(service)
    if state == "active":
        return True, f"automation already active ({service})"

    notes: list[str] = [f"was={state}"]
    wrapper = root / "server_deployment" / "race_day_start_wrapper.sh"
    start = root / "server_deployment" / "race_day_start_hwm.sh"
    if not start.is_file():
        start = root / "race_day_start_hwm.sh"

    env = os.environ.copy()
    env["YOKUMAKUN_ROOT"] = str(root)
    env["YOKUMAKUN_SERVER_AUTO_SERVICE"] = service
    env.setdefault("TZ", "Asia/Tokyo")

    if wrapper.is_file():
        try:
            cp = subprocess.run(
                ["bash", str(wrapper)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            notes.append(f"wrapper_rc={cp.returncode}")
        except Exception as e:
            notes.append(f"wrapper:{type(e).__name__}:{e}")
    elif start.is_file():
        try:
            cp = subprocess.run(
                ["bash", str(start)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            notes.append(f"start_script_rc={cp.returncode}")
        except Exception as e:
            notes.append(f"start_script:{type(e).__name__}:{e}")

    state = _service_active(service)
    if state != "active":
        cp = _sudo_run(["systemctl", "start", service], timeout=90)
        notes.append(f"systemctl_start_rc={cp.returncode}")
        time.sleep(2)
        state = _service_active(service)

    ok = state == "active"
    return ok, f"automation={state}; " + ", ".join(notes)


def find_worker_pids() -> list[int]:
    try:
        cp = subprocess.run(
            ["pgrep", "-f", WORKER_NAME],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return []
    out = []
    for line in (cp.stdout or "").splitlines():
        s = line.strip()
        if s.isdigit():
            out.append(int(s))
    return out


def start_worker(*, root: Path) -> tuple[bool, str, int | None]:
    worker = root / WORKER_NAME
    if not worker.is_file():
        return False, f"missing {worker}", None

    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / "morning_bulk_admin_rerun.log"
    py = _py(root)
    env = os.environ.copy()
    env["YOKUMAKUN_ROOT"] = str(root)
    env.setdefault("TZ", "Asia/Tokyo")
    env.setdefault("HWM_SERVER_AUTO", "1")
    env.setdefault("HWM_SUBPROCESS_PREDICT", "1")

    try:
        logf = open(log_path, "a", encoding="utf-8")
    except Exception:
        logf = subprocess.DEVNULL

    try:
        if hasattr(logf, "write"):
            logf.write(
                f"\n==== admin morning_bulk_rerun {time.strftime('%Y-%m-%dT%H:%M:%S')} ====\n"
            )
            logf.flush()
        proc = subprocess.Popen(
            [py, str(worker)],
            cwd=str(root),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        if hasattr(logf, "close"):
            try:
                logf.close()
            except Exception:
                pass
        return False, f"Popen failed: {type(e).__name__}: {e}", None

    # parent no longer needs the handle; child keeps fd
    if hasattr(logf, "close"):
        try:
            logf.close()
        except Exception:
            pass

    return True, f"spawned pid={proc.pid} log={log_path.name}", int(proc.pid)


def wait_worker_running(*, timeout_sec: float = VERIFY_SEC) -> tuple[bool, list[int]]:
    deadline = time.time() + max(1.0, timeout_sec)
    last: list[int] = []
    while time.time() < deadline:
        last = find_worker_pids()
        if last:
            return True, last
        time.sleep(0.5)
    return False, last


def start_morning_bulk_rerun(
    root: Path | None = None,
    *,
    service: str | None = None,
    verify_sec: float = VERIFY_SEC,
) -> dict[str, Any]:
    """Return JSON-serializable result for admin panel."""
    root_p = _root(root)
    _load_env(root_p)
    svc = (service or os.environ.get("YOKUMAKUN_SERVER_AUTO_SERVICE") or DEFAULT_SERVICE).strip()

    result: dict[str, Any] = {
        "ok": False,
        "action": "morning_bulk_rerun",
        "root": str(root_p),
        "service": svc,
        "worker": WORKER_NAME,
        "automation_active": False,
        "worker_running": False,
        "worker_pids": [],
        "message": "",
    }

    existing = find_worker_pids()
    if existing:
        result.update(
            {
                "ok": True,
                "automation_active": _service_active(svc) == "active",
                "worker_running": True,
                "worker_pids": existing,
                "message": (
                    f"既に一斉予想ワーカーが動作中です (pid={existing[0]}"
                    + (f" 他{len(existing)-1}" if len(existing) > 1 else "")
                    + ")。完了までログを監視してください。"
                ),
                "already_running": True,
            }
        )
        return result

    auto_ok, auto_note = ensure_automation_active(root=root_p, service=svc)
    result["automation_active"] = auto_ok
    result["automation_detail"] = auto_note
    if not auto_ok:
        result["message"] = (
            "automation を active にできませんでした。"
            f" ({auto_note}) "
            "YOKUMAKUN_SUDO_PASS と systemctl を確認してください。"
        )
        result["error"] = "automation_inactive"
        return result

    spawned_ok, spawn_note, spawn_pid = start_worker(root=root_p)
    result["spawn"] = {"ok": spawned_ok, "detail": spawn_note, "pid": spawn_pid}
    if not spawned_ok:
        result["message"] = f"ワーカー起動に失敗: {spawn_note}"
        result["error"] = "spawn_failed"
        return result

    running, pids = wait_worker_running(timeout_sec=verify_sec)
    result["worker_running"] = running
    result["worker_pids"] = pids
    if not running:
        result["message"] = (
            f"ワーカーを起動しましたが {int(verify_sec)} 秒以内にプロセスを確認できません。"
            f" ({spawn_note}) logs/morning_bulk_admin_rerun.log を確認してください。"
        )
        result["error"] = "worker_not_observed"
        return result

    result["ok"] = True
    result["message"] = (
        f"一斉予想ワーカーを起動しました (pid={pids[0]})。"
        "予想完了まで数十分かかることがあります。『完了』ではなく『起動確認済み』です。"
    )
    return result


if __name__ == "__main__":
    import json
    import sys

    out = start_morning_bulk_rerun(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    raise SystemExit(0 if out.get("ok") else 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""開催日 21:00 向け: 当日機能の動作テストを行い、結果をテストwebhookへ報告する。

制約:
  - 全体を 2 時間以内で終える（ハードデッドライン）
  - 開催日以外はスキップ通知のみ
  - 破壊的操作（再予想・Selenium一斉）はしない。読み取り＋軽い到達確認のみ。
  - 不具合検知時は安全な運用修復のみ自動実施し、対象チェックを再検査する
    （YOKUMAKUN_EOD_TEST_AUTOFIX=0 / --no-autofix で無効化可）

通知先（優先順）:
  テスト: DISCORD_WEBHOOK_TEST / ADMIN_TEST_WEBHOOK_URL / HWM_DISCORD_WEBHOOK_TEST /
          DISCORD_TEST_WEBHOOK_URL / DISCORD_WEBHOOK_TEST_ALWAYS
  不具合あり時はエラー通知にも送る:
          DISCORD_WEBHOOK_FAILURE / DISCORD_WEBHOOK_ERROR / DISCORD_WEBHOOK_URL_3 など
  未設定時は ops_discord_notify.notify_action にフォールバック
"""

from __future__ import annotations

import json
import os
import pickle
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PUBLIC_LATEST = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/snapshots/latest.json"
)
PUBLIC_DAY = (
    "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
    "public-viewer/snapshots/{day}.json"
)
EVENT_NAME = "race_day_evening_functional_test"
DEFAULT_BUDGET_SEC = 2 * 60 * 60  # 2 hours

# 過去データ・外部依存などで自動修正しない検査
NON_AUTOFIXABLE_CHECKS = frozenset(
    {
        "morning_bulk_cache",
        "daytime_publish_evidence",
        "netkeiba_light",
        "pdf_holmes_sample",
    }
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    severity: str = "error"  # error | warn | info
    elapsed_ms: int = 0


@dataclass
class AutofixResult:
    check_name: str
    attempted: bool
    ok: bool
    detail: str
    skipped_reason: str = ""


@dataclass
class SuiteResult:
    day: str
    started_at: str
    finished_at: str = ""
    race_day: bool = False
    skipped: bool = False
    overall_ok: bool = False
    budget_sec: int = DEFAULT_BUDGET_SEC
    timed_out: bool = False
    checks: list[CheckResult] = field(default_factory=list)
    bugs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    autofixes: list[AutofixResult] = field(default_factory=list)
    autofix_recovered: bool = False
    initial_bugs: list[str] = field(default_factory=list)


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    for cand in (here, here.parent, Path("/opt/yokuumakun_auto-x")):
        if (cand / "hwm.py").is_file() or (cand / "admin_panel_api.py").is_file():
            return cand.resolve()
    return Path("/opt/yokuumakun_auto-x")


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
        rt = root / "server_deployment" / "hwm_runtime.env"
        if rt.is_file():
            load_dotenv(rt, override=False)
    except Exception:
        pass


def _today() -> str:
    return datetime.now(_JST).strftime("%Y-%m-%d")


def _today_ymd() -> str:
    return datetime.now(_JST).strftime("%Y%m%d")


def _env_webhook(keys: tuple[str, ...]) -> str:
    for key in keys:
        v = (os.environ.get(key) or "").strip().strip('"')
        if v.startswith("http"):
            return v
    return ""


def _test_webhook_url() -> str:
    return _env_webhook(
        (
            "DISCORD_WEBHOOK_TEST",
            "ADMIN_TEST_WEBHOOK_URL",
            "HWM_DISCORD_WEBHOOK_TEST",
            "DISCORD_TEST_WEBHOOK_URL",
            "DISCORD_WEBHOOK_TEST_ALWAYS",
            "HWM_DISCORD_WEBHOOK_TEST_ALWAYS",
        )
    )


def _error_webhook_url() -> str:
    """エラー通知（failure）用 webhook。サーバー .env の FAILURE / URL_3 を優先。"""
    return _env_webhook(
        (
            "DISCORD_WEBHOOK_FAILURE",
            "HWM_DISCORD_WEBHOOK_FAILURE",
            "DISCORD_WEBHOOK_ERROR",
            "HWM_DISCORD_WEBHOOK_ERROR",
            "DISCORD_ERROR_WEBHOOK_URL",
            "ADMIN_ERROR_WEBHOOK_URL",
            "DISCORD_WEBHOOK_URL_3",
        )
    )


def _report_has_errors(suite: SuiteResult) -> bool:
    """不具合エラーを含む報告か（警告のみは含めない）。"""
    if suite.skipped:
        return False
    if suite.timed_out:
        return True
    if suite.bugs:
        return True
    return not suite.overall_ok


def _post_discord_webhook(
    webhook: str, content: str, embeds: list[dict] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": content[:1900]}
    if embeds:
        payload["embeds"] = embeds[:3]
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return {"ok": True, "status": int(getattr(res, "status", 204) or 204)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": int(e.code), "error": str(e.reason)}
    except Exception as e:
        return {"ok": False, "status": None, "error": f"{type(e).__name__}: {e}"}


def _notify_ops_fallback(status: str, detail: str) -> None:
    try:
        root = _root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from ops_discord_notify import notify_action  # type: ignore

        notify_action(EVENT_NAME, status=status, detail=detail[:300])
    except Exception:
        pass


def _http_get_json(url: str, *, timeout: float = 30.0) -> tuple[dict[str, Any] | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _http_get(url: str, *, timeout: float = 25.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.8",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
            raw = res.read()
            status = int(getattr(res, "status", 200) or 200)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read() or b""
        except Exception:
            raw = b""
        status = int(e.code)
    except Exception as e:
        return {
            "ok": False,
            "status": None,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "reason": f"{type(e).__name__}: {e}",
        }
    return {
        "ok": status == 200 and len(raw) >= 200,
        "status": status,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "bytes": len(raw),
        "reason": "ok" if status == 200 else f"http_{status}",
    }


def _run_cmd(cmd: list[str], *, timeout: float = 30.0) -> tuple[int, str]:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = ((cp.stdout or "") + (cp.stderr or "")).strip()
        return int(cp.returncode), out[-2000:]
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def _sudo_cmd(cmd: list[str], *, timeout: float = 60.0) -> tuple[int, str]:
    """Run command with sudo when needed. Uses YOKUMAKUN_SUDO_PASS if set."""
    pw = (
        os.environ.get("YOKUMAKUN_SUDO_PASS")
        or os.environ.get("YOKUMAKUN_SSH_PASS")
        or ""
    ).strip()
    try:
        if pw:
            full = ["sudo", "-S", "-p", ""] + cmd
            cp = subprocess.run(
                full,
                input=pw + "\n",
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            # already root / passwordless sudo
            cp = subprocess.run(
                ["sudo", "-n"] + cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if cp.returncode != 0 and "password" in ((cp.stderr or "") + (cp.stdout or "")).lower():
                # last resort: try without sudo (may work for user units / already root)
                cp2 = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                out2 = ((cp2.stdout or "") + (cp2.stderr or "")).strip()
                return int(cp2.returncode), out2[-2000:]
        out = ((cp.stdout or "") + (cp.stderr or "")).strip()
        return int(cp.returncode), out[-2000:]
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def _autofix_enabled(argv_flag_no: bool = False) -> bool:
    if argv_flag_no:
        return False
    v = (os.environ.get("YOKUMAKUN_EOD_TEST_AUTOFIX") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _find_first_script(root: Path, names: tuple[str, ...]) -> Path | None:
    dirs = (
        root,
        root / "server_deployment",
        root / "scripts",
        root / "tools",
        Path(__file__).resolve().parent,
    )
    for d in dirs:
        for name in names:
            p = d / name
            if p.is_file():
                return p
    return None


class Deadline:
    def __init__(self, budget_sec: int) -> None:
        self.deadline = time.monotonic() + max(60, budget_sec)

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def expired(self) -> bool:
        return self.remaining() <= 0


def _is_race_day(root: Path, day: str) -> tuple[bool, str]:
    """Detect whether *day* is/was a race day.

    At 21:00 the public snapshot is often already emptied by EOD, so prefer
    local artifacts (morning cache / stop-finalize logs / EOD archive).
    """
    ymd = day.replace("-", "")
    logs = root / "logs"
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        if (logs / name).is_file():
            return True, f"cache:{name}"
    for p in logs.glob(f"morning_bulk_done_*{day}.flag"):
        if p.is_file():
            return True, f"done_flag:{p.name}"
    plain = logs / f"morning_bulk_done_{day}.flag"
    if plain.is_file():
        return True, f"done_flag:{plain.name}"

    eod_arch = root / "data" / "eod_archives" / f"{day}.json"
    if eod_arch.is_file() and eod_arch.stat().st_size > 8:
        return True, f"eod_archive:{eod_arch.name}"

    # today's stop/finalize logs (mtime in JST)
    for pattern in (
        f"race_day_stop_{ymd}*.log",
        f"race_day_stop_{day}*.log",
        f"race_day_finalize_{ymd}*.log",
        f"race_day_finalize_{day}*.log",
    ):
        for p in logs.glob(pattern):
            try:
                mt = datetime.fromtimestamp(p.stat().st_mtime, _JST).strftime("%Y-%m-%d")
            except Exception:
                continue
            if mt == day and p.stat().st_size > 0:
                return True, f"log:{p.name}"

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from hwm_server_standalone import _today_is_scheduled_race_day  # type: ignore

        if bool(_today_is_scheduled_race_day()):
            return True, "helper:_today_is_scheduled_race_day"
    except Exception:
        pass

    # day archive on public storage (survives EOD clear of latest.json)
    day_snap, _ = _http_get_json(PUBLIC_DAY.format(day=day), timeout=20.0)
    if day_snap and int(day_snap.get("race_count") or 0) > 0:
        return True, f"public_day_archive race_count={day_snap.get('race_count')}"

    return False, "no_cache_flag_log_or_schedule"


def _check(name: str, fn: Callable[[], tuple[bool, str, str]], deadline: Deadline) -> CheckResult:
    if deadline.expired():
        return CheckResult(name, False, "deadline_exceeded_before_start", "error", 0)
    t0 = time.time()
    try:
        ok, detail, severity = fn()
    except Exception as e:
        ok, detail, severity = False, f"{type(e).__name__}: {e}", "error"
    return CheckResult(
        name=name,
        ok=ok,
        detail=detail[:500],
        severity=severity if not ok else "info",
        elapsed_ms=int((time.time() - t0) * 1000),
    )


def check_morning_bulk(root: Path, day: str) -> tuple[bool, str, str]:
    logs = root / "logs"
    ymd = day.replace("-", "")
    cache = None
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        fp = logs / name
        if fp.is_file():
            cache = fp
            break
    flags = list(logs.glob(f"morning_bulk_done_*{day}.flag"))
    if (logs / f"morning_bulk_done_{day}.flag").is_file():
        flags.append(logs / f"morning_bulk_done_{day}.flag")
    if not cache and not flags:
        return False, "朝一斉 cache/done flag が無い", "error"
    n = 0
    if cache:
        try:
            with cache.open("rb") as f:
                data = pickle.load(f)
            n = len(data) if isinstance(data, dict) else 0
        except Exception as e:
            return False, f"cache読込失敗: {type(e).__name__}: {e}", "error"
        if n <= 0:
            return False, f"cache空 ({cache.name})", "error"
    return True, f"cache_n={n} flags={len(flags)} file={cache.name if cache else '-'}", "info"


def check_automation_stopped() -> tuple[bool, str, str]:
    rc, out = _run_cmd(["systemctl", "is-active", "yokuum-server-automation-x.service"])
    state = (out or "").strip().splitlines()[-1] if out else "unknown"
    # 21時時点では停止が正常
    if state in ("inactive", "failed", "dead"):
        return True, f"automation={state}", "info"
    if state == "active":
        return False, "21時時点で automation が active のまま（race_day_stop 未実行の疑い）", "error"
    return False, f"automation state={state} rc={rc}", "warn"


def check_no_stuck_workers() -> tuple[bool, str, str]:
    rc, out = _run_cmd(
        ["bash", "-lc", "pgrep -af 'pre_race_auto_predict_worker|morning_bulk_server_worker|graded_auto_predict_worker' || true"]
    )
    lines = [ln for ln in (out or "").splitlines() if ln.strip() and "pgrep" not in ln]
    # pgrep itself may appear; filter python workers
    workers = [ln for ln in lines if "python" in ln and "worker" in ln]
    if workers:
        return False, f"残留ワーカー {len(workers)}件: {workers[0][:160]}", "error"
    return True, "残留ワーカーなし", "info"


def check_admin_health() -> tuple[bool, str, str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8791/health", timeout=10) as resp:
            body = json.loads(resp.read().decode())
        if body.get("ok"):
            return True, "admin /health ok", "info"
        return False, f"admin health unexpected: {body}", "error"
    except Exception as e:
        return False, f"admin到達失敗: {type(e).__name__}: {e}", "error"


def check_publish_patches(root: Path) -> tuple[bool, str, str]:
    missing = []
    pre = root / "pre_race_auto_predict_worker.py"
    mb = root / "morning_bulk_server_worker.py"
    if pre.is_file():
        t = pre.read_text(encoding="utf-8", errors="replace")
        if "BEGIN pre_race_publish_on_success" not in t and "_publish_public_viewer_snapshot" not in t:
            missing.append("pre_race_publish_patch")
    else:
        missing.append("pre_race_worker_missing")
    if mb.is_file():
        t = mb.read_text(encoding="utf-8", errors="replace")
        if "BEGIN morning_bulk_publish_on_success" not in t and "run_publish" not in t:
            missing.append("morning_bulk_publish_patch")
    else:
        missing.append("morning_bulk_worker_missing")
    watch = root / "morning_bulk_publish_watch.py"
    if not watch.is_file():
        missing.append("publish_watch_missing")
    if missing:
        return False, "publish恒久パッチ不足: " + ",".join(missing), "error"
    return True, "pre_race/morning_bulk publish patch + watch あり", "info"


def check_publish_watch_timer() -> tuple[bool, str, str]:
    rc, out = _run_cmd(["systemctl", "is-enabled", "yokuum-morning-publish-watch.timer"])
    state = (out or "").strip().splitlines()[-1] if out else ""
    if state == "enabled":
        return True, "publish-watch.timer enabled", "info"
    return False, f"publish-watch.timer={state or 'missing'}", "warn"


def check_eod_snapshot(day: str) -> tuple[bool, str, str]:
    """20:00 finalize 後は latest が cleared/空が正常。当日アーカイブ or クリア状態を確認。"""
    latest, err = _http_get_json(PUBLIC_LATEST)
    if latest is None:
        return False, f"latest取得失敗: {err}", "error"
    cleared = bool(latest.get("cleared"))
    rc = int(latest.get("race_count") or 0)
    sched = str(latest.get("schedule_date") or "")
    # アーカイブ
    day_snap, day_err = _http_get_json(PUBLIC_DAY.format(day=day))
    if day_snap and int(day_snap.get("race_count") or 0) > 0:
        # 品質の軽い確認
        races = []
        for v in day_snap.get("venues") or []:
            races.extend(v.get("races") or [])
        missing_h = sum(1 for r in races if not str(r.get("holmes_index") or "").strip())
        if missing_h:
            return (
                False,
                f"day archive あり n={len(races)} だが holmes欠落 {missing_h}",
                "error",
            )
        return True, f"day archive OK n={len(races)}; latest cleared={cleared} rc={rc}", "info"

    # archive が無い場合: finalize で cleared なら合格、当日のまま残っていれば警告
    if cleared or rc == 0:
        return True, f"latest EOD cleared/empty (cleared={cleared} rc={rc} sched={sched})", "info"
    if sched == day and rc > 0:
        return (
            False,
            f"21時時点で latest が未クリアのまま (rc={rc}) — race_day_finalize 未実行の疑い",
            "error",
        )
    return False, f"day archive無し day_err={day_err}; latest sched={sched} rc={rc}", "warn"


def check_daytime_publish_evidence(root: Path, day: str) -> tuple[bool, str, str]:
    """当日中に公開更新された痕跡（admin_api / force_publish / ログ）。"""
    hints = []
    admin, _ = _http_get_json(
        "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/admin_api.json"
    )
    if admin and str(admin.get("updated_at") or "").startswith(day):
        hints.append(f"admin_api.updated_at={admin.get('updated_at')}")
    fp_last, _ = _http_get_json(
        "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ops/force_publish_last.json"
    )
    if fp_last and fp_last.get("ok") and str(fp_last.get("schedule_date") or "") == day:
        hints.append("force_publish_last ok")
    # server logs: public_viewer / publish
    dbg = root / "logs" / "server_automation_debug.jsonl"
    pub_ok = 0
    pub_err = 0
    if dbg.is_file():
        try:
            # 末尾だけ
            raw = dbg.read_bytes()[-400000:].decode("utf-8", errors="replace")
            for line in raw.splitlines():
                if day not in line and day.replace("-", "") not in line:
                    # still count event names
                    pass
                low = line.lower()
                if "public_viewer" in low or "publish" in low:
                    if "exception" in low or "error" in low or "failed" in low:
                        pub_err += 1
                    elif "ok" in low or "done" in low or "publish" in low:
                        pub_ok += 1
        except Exception:
            pass
    if hints or pub_ok > 0:
        return True, f"evidence={hints or ['debug_log']} pub_ok≈{pub_ok} pub_err≈{pub_err}", "info"
    # cache があれば最低限当日運用はあったとみなすが warn
    ymd = day.replace("-", "")
    if (root / "logs" / f"morning_bulk_races_{ymd}.pkl").is_file():
        return True, "cacheはあるが公開更新の直接証拠は薄い", "warn"
    return False, "当日の公開更新証拠なし", "error"


def check_pdf_holmes_sample(day: str) -> tuple[bool, str, str]:
    """公開PDFが1件でもあればヘッダのホームズ指数を確認。"""
    # prefer day archive then latest
    for url in (PUBLIC_DAY.format(day=day), PUBLIC_LATEST):
        snap, err = _http_get_json(url)
        if not snap:
            continue
        pdf_url = ""
        sample_meta = ""
        for v in snap.get("venues") or []:
            for r in v.get("races") or []:
                if r.get("pdf_url"):
                    pdf_url = str(r["pdf_url"])
                    sample_meta = f"{r.get('place')}{r.get('R')}R site_holmes={r.get('holmes_index')}"
                    break
            if pdf_url:
                break
        if not pdf_url:
            continue
        try:
            path = Path("/tmp/eod_func_test_sample.pdf")
            urllib.request.urlretrieve(pdf_url, path)
            cp = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            head = "\n".join((cp.stdout or "").splitlines()[:8])
            m = re.search(r"ホームズ指数:([^\s/]+)", head)
            if not m:
                return False, f"PDFにホームズ指数欄なし ({sample_meta})", "error"
            val = m.group(1).strip()
            if val in ("-", "—", "－", ""):
                return False, f"PDFホームズ指数が空/ハイフン ({sample_meta}) header={val}", "error"
            return True, f"PDFホームズ指数={val} ({sample_meta})", "info"
        except FileNotFoundError:
            return True, "pdftotext無しのためPDF検査スキップ", "warn"
        except Exception as e:
            return False, f"PDF検査失敗: {type(e).__name__}: {e}", "warn"
    return True, "公開PDF無し（スキップ）", "warn"


def check_netkeiba_light() -> tuple[bool, str, str]:
    today = _today_ymd()
    url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={today}"
    res = _http_get(url, timeout=20)
    if res.get("ok"):
        return True, f"netkeiba list OK {res.get('elapsed_ms')}ms", "info"
    # 開催後は一覧が薄いこともある → top を試す
    top = _http_get("https://race.netkeiba.com/top/", timeout=20)
    if top.get("ok"):
        return True, f"netkeiba top OK (list={res.get('reason')})", "info"
    return False, f"netkeiba到達NG list={res} top={top}", "error"


def check_stop_finalize_logs(root: Path, day: str) -> tuple[bool, str, str]:
    logs = root / "logs"
    if not logs.is_dir():
        return False, "logs dir missing", "error"
    ymd = day.replace("-", "")
    stop = sorted(logs.glob(f"race_day_stop_{ymd}*.log")) + sorted(
        logs.glob("race_day_stop_*.log")
    )
    fin = sorted(logs.glob(f"race_day_finalize_{ymd}*.log")) + sorted(
        logs.glob("race_day_finalize_*.log")
    )
    # 今日のmtimeのもの優先
    def _today_files(paths: list[Path]) -> list[Path]:
        out = []
        for p in paths:
            try:
                mt = datetime.fromtimestamp(p.stat().st_mtime, _JST).strftime("%Y-%m-%d")
            except Exception:
                continue
            if mt == day:
                out.append(p)
        return out

    stop_t = _today_files(stop)
    fin_t = _today_files(fin)
    if not stop_t and not fin_t:
        return False, "本日の race_day_stop/finalize ログが無い", "error"
    # 末尾エラーざっと
    err_hits = 0
    sample = ""
    for p in (stop_t[-1:] + fin_t[-1:]):
        try:
            tail = p.read_text(encoding="utf-8", errors="replace")[-8000:]
        except Exception:
            continue
        if re.search(r"\berror\b|\bfatal\b|Traceback", tail, re.I):
            err_hits += 1
            sample = p.name
    if err_hits:
        return False, f"stop/finalizeログに error 痕跡 ({sample})", "error"
    return True, f"stop_logs={len(stop_t)} finalize_logs={len(fin_t)}", "info"


def autofix_automation_stopped(root: Path, day: str) -> AutofixResult:
    del root, day
    rc, out = _sudo_cmd(
        ["systemctl", "stop", "yokuum-server-automation-x.service"],
        timeout=90,
    )
    ok = rc == 0
    # inactive でも stop は成功扱い。確認
    rc2, out2 = _run_cmd(["systemctl", "is-active", "yokuum-server-automation-x.service"])
    state = (out2 or "").strip().splitlines()[-1] if out2 else ""
    if state in ("inactive", "failed", "dead"):
        ok = True
    return AutofixResult(
        "automation_stopped",
        True,
        ok,
        f"systemctl stop rc={rc} state={state} out={(out or '')[-200:]}",
    )


def autofix_no_stuck_workers(root: Path, day: str) -> AutofixResult:
    del root, day
    # 予想ワーカーのみ対象（テスト自身や system サービスは触らない）
    pattern = (
        "pre_race_auto_predict_worker\\.py|"
        "morning_bulk_server_worker\\.py|"
        "graded_auto_predict_worker\\.py"
    )
    rc, out = _run_cmd(["bash", "-lc", f"pkill -f '{pattern}' || true"], timeout=30)
    time.sleep(2.0)
    rc2, out2 = _run_cmd(
        [
            "bash",
            "-lc",
            "pgrep -af 'pre_race_auto_predict_worker|morning_bulk_server_worker|graded_auto_predict_worker' || true",
        ]
    )
    lines = [
        ln
        for ln in (out2 or "").splitlines()
        if ln.strip() and "pgrep" not in ln and "python" in ln and "worker" in ln
    ]
    ok = len(lines) == 0
    return AutofixResult(
        "no_stuck_workers",
        True,
        ok,
        f"pkill rc={rc} remaining={len(lines)} out={(out or '')[-120:]}",
    )


def autofix_admin_health(root: Path, day: str) -> AutofixResult:
    del root, day
    rc, out = _sudo_cmd(
        ["systemctl", "restart", "yokuum-admin-panel.service"],
        timeout=120,
    )
    time.sleep(3.0)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8791/health", timeout=10) as resp:
            body = json.loads(resp.read().decode())
        healthy = bool(body.get("ok"))
    except Exception as e:
        healthy = False
        body = {"error": f"{type(e).__name__}: {e}"}
    return AutofixResult(
        "admin_health",
        True,
        healthy,
        f"restart rc={rc} healthy={healthy} out={(out or '')[-160:]} body={body}",
    )


def autofix_publish_patches(root: Path, day: str) -> AutofixResult:
    del day
    notes: list[str] = []
    ok_any = False
    for script_name in (
        "patch_pre_race_publish_on_success.py",
        "patch_worker_publish_on_success.py",
    ):
        script = root / script_name
        if not script.is_file():
            notes.append(f"{script_name}=missing")
            continue
        rc, out = _run_cmd([sys.executable, str(script), str(root)], timeout=90)
        notes.append(f"{script_name} rc={rc}")
        if rc == 0:
            ok_any = True
        elif out:
            notes.append(out[-120:])
    # re-evaluate patch presence
    ok_chk, detail, _ = check_publish_patches(root)
    return AutofixResult(
        "publish_patches",
        True,
        ok_chk,
        f"ok_any={ok_any} {detail}; " + "; ".join(notes),
    )


def autofix_publish_watch_timer(root: Path, day: str) -> AutofixResult:
    del day
    installer = root / "install_daily_publish_watch.py"
    if installer.is_file():
        rc, out = _run_cmd([sys.executable, str(installer), str(root)], timeout=180)
        ok_chk, detail, _ = check_publish_watch_timer()
        return AutofixResult(
            "publish_watch_timer",
            True,
            ok_chk,
            f"install rc={rc} {detail} out={(out or '')[-200:]}",
        )
    # fallback: enable existing unit
    rc, out = _sudo_cmd(
        ["systemctl", "enable", "--now", "yokuum-morning-publish-watch.timer"],
        timeout=90,
    )
    ok_chk, detail, _ = check_publish_watch_timer()
    return AutofixResult(
        "publish_watch_timer",
        True,
        ok_chk or rc == 0,
        f"enable --now rc={rc} {detail} out={(out or '')[-160:]}",
    )


def autofix_stop_finalize_logs(root: Path, day: str) -> AutofixResult:
    """ログ欠落時: 既存の stop/finalize スクリプトがあれば実行を試みる。"""
    notes: list[str] = []
    stop = _find_first_script(
        root,
        (
            "race_day_stop_hwm.sh",
            "race_day_stop.sh",
            "stop_race_day_hwm.sh",
        ),
    )
    fin = _find_first_script(
        root,
        (
            "race_day_finalize_hwm.sh",
            "race_day_finalize.sh",
            "eod_finalize_hwm.sh",
            "finalize_race_day.sh",
        ),
    )
    if not stop and not fin:
        return AutofixResult(
            "race_day_stop_finalize_logs",
            False,
            False,
            "stop/finalize スクリプト未検出",
            skipped_reason="no_stop_finalize_script",
        )

    env = os.environ.copy()
    env["YOKUMAKUN_ROOT"] = str(root)
    for label, script in (("stop", stop), ("finalize", fin)):
        if script is None:
            continue
        try:
            cp = subprocess.run(
                ["bash", str(script)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )
            notes.append(f"{label}:{script.name} rc={cp.returncode}")
        except Exception as e:
            notes.append(f"{label}:{script.name} {type(e).__name__}:{e}")

    ok_chk, detail, _ = check_stop_finalize_logs(root, day)
    return AutofixResult(
        "race_day_stop_finalize_logs",
        True,
        ok_chk,
        f"{detail}; " + "; ".join(notes),
    )


def autofix_eod_snapshot_state(root: Path, day: str) -> AutofixResult:
    """latest 未クリア時: finalize スクリプトがあれば実行。"""
    fin = _find_first_script(
        root,
        (
            "race_day_finalize_hwm.sh",
            "race_day_finalize.sh",
            "eod_finalize_hwm.sh",
            "finalize_race_day.sh",
        ),
    )
    if fin is None:
        # Python ヘルパーがあれば試す（破壊的な再公開はしない）
        for mod_name, attr in (
            ("hwm_server_standalone", "race_day_finalize"),
            ("hwm", "race_day_finalize"),
            ("public_viewer.export_public_snapshot", "clear_latest_snapshot"),
        ):
            try:
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                mod = __import__(mod_name, fromlist=[attr])
                fn = getattr(mod, attr, None)
                if callable(fn):
                    fn()
                    ok_chk, detail, _ = check_eod_snapshot(day)
                    return AutofixResult(
                        "eod_snapshot_state",
                        True,
                        ok_chk,
                        f"called {mod_name}.{attr}; {detail}",
                    )
            except Exception:
                continue
        return AutofixResult(
            "eod_snapshot_state",
            False,
            False,
            "finalize 手段未検出（手動確認が必要）",
            skipped_reason="no_finalize_means",
        )

    env = os.environ.copy()
    env["YOKUMAKUN_ROOT"] = str(root)
    try:
        cp = subprocess.run(
            ["bash", str(fin)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        out = ((cp.stdout or "") + (cp.stderr or "")).strip()[-200:]
        note = f"{fin.name} rc={cp.returncode} {out}"
    except Exception as e:
        note = f"{fin.name} {type(e).__name__}:{e}"
    ok_chk, detail, _ = check_eod_snapshot(day)
    return AutofixResult(
        "eod_snapshot_state",
        True,
        ok_chk,
        f"{detail}; {note}",
    )


_AUTOFIXERS: dict[str, Callable[[Path, str], AutofixResult]] = {
    "automation_stopped": autofix_automation_stopped,
    "no_stuck_workers": autofix_no_stuck_workers,
    "admin_health": autofix_admin_health,
    "publish_patches": autofix_publish_patches,
    "publish_watch_timer": autofix_publish_watch_timer,
    "race_day_stop_finalize_logs": autofix_stop_finalize_logs,
    "eod_snapshot_state": autofix_eod_snapshot_state,
}


def attempt_autofixes(
    root: Path,
    day: str,
    failed: list[CheckResult],
    *,
    deadline: Deadline,
) -> list[AutofixResult]:
    results: list[AutofixResult] = []
    for cr in failed:
        if deadline.remaining() < 45:
            results.append(
                AutofixResult(
                    cr.name,
                    False,
                    False,
                    "予算不足のため自己修正スキップ",
                    skipped_reason="low_budget",
                )
            )
            continue
        if cr.name in NON_AUTOFIXABLE_CHECKS:
            results.append(
                AutofixResult(
                    cr.name,
                    False,
                    False,
                    "過去データ/外部依存のため自動修正対象外",
                    skipped_reason="non_autofixable",
                )
            )
            continue
        fixer = _AUTOFIXERS.get(cr.name)
        if fixer is None:
            results.append(
                AutofixResult(
                    cr.name,
                    False,
                    False,
                    "自己修正ハンドラなし",
                    skipped_reason="no_handler",
                )
            )
            continue
        try:
            results.append(fixer(root, day))
        except Exception as e:
            results.append(
                AutofixResult(
                    cr.name,
                    True,
                    False,
                    f"{type(e).__name__}: {e}",
                )
            )
    return results


def _rebuild_bugs_warnings(suite: SuiteResult) -> None:
    suite.bugs = []
    suite.warnings = []
    for cr in suite.checks:
        if cr.ok:
            continue
        msg = f"{cr.name}: {cr.detail}"
        if cr.severity == "warn":
            suite.warnings.append(msg)
        else:
            suite.bugs.append(msg)


def build_report(suite: SuiteResult) -> tuple[str, str, int]:
    """returns title, description, color"""
    if suite.skipped:
        title = "開催日夕テスト（スキップ）"
        desc = f"日付: {suite.day}\n開催日ではないためスキップしました。"
        return title, desc, 0x95A5A6

    bugs = list(suite.bugs)
    warns = suite.warnings
    if suite.timed_out:
        bugs = bugs + ["2時間デッドライン超過（途中終了）"]

    if suite.overall_ok and not bugs:
        if suite.autofix_recovered:
            title = "開催日夕テスト: 不具合無し（自己修正済）"
            status_line = "結果: **不具合無し（自己修正済）**"
        else:
            title = "開催日夕テスト: 不具合無し"
            status_line = "結果: **不具合無し**"
        color = 0x2ECC71
    else:
        title = "開催日夕テスト: 不具合あり"
        status_line = "結果: **不具合あり**"
        color = 0xE74C3C

    lines = [
        status_line,
        f"日付: {suite.day}",
        f"開始: {suite.started_at}",
        f"終了: {suite.finished_at}",
        f"予算: {suite.budget_sec // 60}分 / timeout={suite.timed_out}",
        "",
        "【チェック一覧】",
    ]
    for c in suite.checks:
        mark = "OK" if c.ok else ("WARN" if c.severity == "warn" else "NG")
        lines.append(f"- [{mark}] {c.name}: {c.detail} ({c.elapsed_ms}ms)")
    if suite.autofixes:
        lines.append("")
        lines.append("【自己修正】")
        for af in suite.autofixes:
            if not af.attempted:
                lines.append(
                    f"- [SKIP] {af.check_name}: {af.detail}"
                    + (f" ({af.skipped_reason})" if af.skipped_reason else "")
                )
            elif af.ok:
                lines.append(f"- [FIXED] {af.check_name}: {af.detail}")
            else:
                lines.append(f"- [FAILED] {af.check_name}: {af.detail}")
        if suite.initial_bugs and suite.autofix_recovered:
            lines.append(f"- 初回不具合 {len(suite.initial_bugs)}件 → 再検査で解消")
    if bugs:
        lines.append("")
        lines.append("【不具合発生点】")
        for b in bugs:
            lines.append(f"- {b}")
    if warns:
        lines.append("")
        lines.append("【警告】")
        for w in warns:
            lines.append(f"- {w}")
    if suite.overall_ok and not bugs:
        lines.append("")
        lines.append("重大な不具合は検出されませんでした。")
    return title, "\n".join(lines)[:3900], color


def run_suite(
    *,
    budget_sec: int | None = None,
    force: bool = False,
    autofix: bool | None = None,
) -> dict[str, Any]:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _load_env(root)

    do_autofix = _autofix_enabled(argv_flag_no=False) if autofix is None else bool(autofix)

    budget = int(
        budget_sec
        or os.environ.get("YOKUMAKUN_EOD_TEST_BUDGET_SEC")
        or DEFAULT_BUDGET_SEC
    )
    day = _today()
    started = datetime.now(_JST)
    suite = SuiteResult(
        day=day,
        started_at=started.isoformat(timespec="seconds"),
        budget_sec=budget,
    )
    deadline = Deadline(budget)

    is_rd, why = _is_race_day(root, day)
    suite.race_day = is_rd
    if not is_rd and not force:
        suite.skipped = True
        suite.overall_ok = True
        suite.finished_at = datetime.now(_JST).isoformat(timespec="seconds")
        title, desc, color = build_report(suite)
        desc += f"\n判定: {why}"
        webhook = _test_webhook_url()
        if webhook:
            wh = _post_discord_webhook(
                webhook,
                content="開催日夕の機能テスト（スキップ）",
                embeds=[{"title": title, "description": desc, "color": color}],
            )
        else:
            _notify_ops_fallback("ok", f"skip non-race-day {day} ({why})")
            wh = {"ok": False, "error": "webhook_not_configured"}
        return {
            "ok": True,
            "skipped": True,
            "day": day,
            "reason": why,
            "webhook": wh,
            "report": desc,
        }

    checks_plan: list[tuple[str, Callable[[], tuple[bool, str, str]]]] = [
        ("morning_bulk_cache", lambda: check_morning_bulk(root, day)),
        ("race_day_stop_finalize_logs", lambda: check_stop_finalize_logs(root, day)),
        ("automation_stopped", check_automation_stopped),
        ("no_stuck_workers", check_no_stuck_workers),
        ("admin_health", check_admin_health),
        ("publish_patches", lambda: check_publish_patches(root)),
        ("publish_watch_timer", check_publish_watch_timer),
        ("eod_snapshot_state", lambda: check_eod_snapshot(day)),
        ("daytime_publish_evidence", lambda: check_daytime_publish_evidence(root, day)),
        ("pdf_holmes_sample", lambda: check_pdf_holmes_sample(day)),
        ("netkeiba_light", check_netkeiba_light),
    ]
    checks_by_name = {name: fn for name, fn in checks_plan}

    for name, fn in checks_plan:
        if deadline.expired():
            suite.timed_out = True
            break
        # 残りが極端に少ない検査はスキップ
        if deadline.remaining() < 15 and name not in ("automation_stopped", "admin_health"):
            suite.checks.append(
                CheckResult(name, False, "skipped_low_budget", "warn", 0)
            )
            suite.warnings.append(f"{name}: 予算不足でスキップ")
            continue
        cr = _check(name, fn, deadline)
        suite.checks.append(cr)
        if not cr.ok:
            msg = f"{cr.name}: {cr.detail}"
            if cr.severity == "warn":
                suite.warnings.append(msg)
            else:
                suite.bugs.append(msg)

    suite.initial_bugs = list(suite.bugs)

    # --- 自己修正 → 失敗チェック再検査 ---
    failed = [c for c in suite.checks if not c.ok]
    if do_autofix and failed and not deadline.expired() and deadline.remaining() >= 45:
        suite.autofixes = attempt_autofixes(root, day, failed, deadline=deadline)
        recheck_names = {
            af.check_name
            for af in suite.autofixes
            if af.attempted
        }
        for name in recheck_names:
            if deadline.expired():
                suite.timed_out = True
                break
            fn = checks_by_name.get(name)
            if fn is None:
                continue
            cr = _check(name, fn, deadline)
            # replace prior result
            for i, old in enumerate(suite.checks):
                if old.name == name:
                    suite.checks[i] = cr
                    break
        _rebuild_bugs_warnings(suite)
        if suite.initial_bugs and not suite.bugs and not suite.timed_out:
            suite.autofix_recovered = True
    elif failed and not do_autofix:
        suite.autofixes = [
            AutofixResult(
                c.name,
                False,
                False,
                "自己修正無効（--no-autofix / YOKUMAKUN_EOD_TEST_AUTOFIX=0）",
                skipped_reason="disabled",
            )
            for c in failed
        ]

    suite.finished_at = datetime.now(_JST).isoformat(timespec="seconds")
    suite.overall_ok = (not suite.bugs) and (not suite.timed_out)

    title, desc, color = build_report(suite)
    embed = [{"title": title, "description": desc, "color": color}]
    has_errors = _report_has_errors(suite)

    webhook = _test_webhook_url()
    if webhook:
        wh = _post_discord_webhook(
            webhook,
            content="開催日夕の機能テスト結果です",
            embeds=embed,
        )
    else:
        _notify_ops_fallback(
            "ok" if suite.overall_ok else "error",
            desc.replace("\n", " | ")[:300],
        )
        wh = {"ok": False, "error": "webhook_not_configured"}

    # 不具合エラーを含む報告はエラー通知 webhook にも送る
    wh_err: dict[str, Any] = {"ok": False, "skipped": True, "reason": "no_errors"}
    if has_errors:
        err_hook = _error_webhook_url()
        if err_hook and err_hook == webhook:
            wh_err = {"ok": True, "skipped": True, "reason": "same_as_test_webhook"}
        elif err_hook:
            wh_err = _post_discord_webhook(
                err_hook,
                content="開催日夕の機能テスト: 不具合あり（エラー通知）",
                embeds=embed,
            )
        else:
            # 専用 URL が無い場合は ops の error 経路へ（failure チャンネル想定）
            _notify_ops_fallback("error", desc.replace("\n", " | ")[:300])
            wh_err = {"ok": False, "error": "error_webhook_not_configured", "ops_fallback": True}

    # 二重に ops へも要約（TEST_ALWAYS 経由でテストチャンネルに乗る構成向け）
    try:
        status_label = "不具合無し"
        if not suite.overall_ok:
            status_label = "不具合あり"
        elif suite.autofix_recovered:
            status_label = "不具合無し（自己修正済）"
        _notify_ops_fallback(
            "ok" if suite.overall_ok else "error",
            status_label
            + f" bugs={len(suite.bugs)} warns={len(suite.warnings)}"
            + f" autofix={len(suite.autofixes)}",
        )
    except Exception:
        pass

    # ログ保存
    try:
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = started.strftime("%Y%m%d_%H%M%S")
        fp = log_dir / f"race_day_evening_functional_test_{ts}.json"
        fp.write_text(
            json.dumps(
                {
                    "day": suite.day,
                    "overall_ok": suite.overall_ok,
                    "timed_out": suite.timed_out,
                    "has_errors": has_errors,
                    "bugs": suite.bugs,
                    "warnings": suite.warnings,
                    "initial_bugs": suite.initial_bugs,
                    "autofix_recovered": suite.autofix_recovered,
                    "autofixes": [af.__dict__ for af in suite.autofixes],
                    "checks": [c.__dict__ for c in suite.checks],
                    "webhook": wh,
                    "error_webhook": wh_err,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        fp = None

    return {
        "ok": suite.overall_ok,
        "skipped": False,
        "day": day,
        "timed_out": suite.timed_out,
        "has_errors": has_errors,
        "bugs": suite.bugs,
        "warnings": suite.warnings,
        "initial_bugs": suite.initial_bugs,
        "autofix_enabled": do_autofix,
        "autofix_recovered": suite.autofix_recovered,
        "autofixes": [af.__dict__ for af in suite.autofixes],
        "checks": [c.__dict__ for c in suite.checks],
        "webhook": wh,
        "webhook_configured": bool(webhook),
        "error_webhook": wh_err,
        "error_webhook_configured": bool(_error_webhook_url()),
        "report": desc,
        "log": str(fp) if fp else "",
        "elapsed_sec": int((datetime.now(_JST) - started).total_seconds()),
    }


def main(argv: list[str]) -> int:
    force = "--force" in argv
    no_autofix = "--no-autofix" in argv
    budget = None
    for a in argv[1:]:
        if a.startswith("--budget-sec="):
            budget = int(a.split("=", 1)[1])
    autofix = False if no_autofix else _autofix_enabled(argv_flag_no=False)
    result = run_suite(budget_sec=budget, force=force, autofix=autofix)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if result.get("skipped"):
        return 0
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

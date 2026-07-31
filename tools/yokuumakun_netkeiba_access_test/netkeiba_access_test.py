#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""サーバーから netkeiba レース情報へ到達できるかのアクセステスト。

管理パネル API（admin_panel_api.py）から呼び出される。
結果はテスト用 Discord Webhook（DISCORD_WEBHOOK_TEST 等）へ通知する。
"""

from __future__ import annotations

import json
import os
import pickle
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_DENY_MARKERS = (
    "access denied",
    "request blocked",
    "just a moment",
    "cf-browser-verification",
    "attention required",
    "sorry, you have been blocked",
    "403 forbidden",
    "429 too many",
    "一時的にアクセスを制限",
    "アクセスが集中",
    "ご利用を制限",
    "captcha",
)


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "admin_panel_api.py").is_file():
        return here
    if (here.parent / "admin_panel_api.py").is_file():
        return here.parent
    return here


def _today_ymd() -> str:
    return datetime.now(_JST).strftime("%Y%m%d")


def _test_webhook_url() -> str:
    for key in (
        "DISCORD_WEBHOOK_TEST",
        "ADMIN_TEST_WEBHOOK_URL",
        "HWM_DISCORD_WEBHOOK_TEST",
        "DISCORD_TEST_WEBHOOK_URL",
    ):
        v = (os.environ.get(key) or "").strip()
        if v.startswith("http"):
            return v
    return ""


def _decode_body(raw: bytes) -> str:
    for enc in ("utf-8", "euc-jp", "cp932", "latin-1"):
        try:
            return raw.decode(enc, errors="replace")
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _http_get(url: str, *, timeout: float = 25.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
            raw = res.read()
            status = int(getattr(res, "status", 200) or 200)
            ctype = res.headers.get("Content-Type") or ""
            final_url = res.geturl()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read() or b""
        except Exception:
            raw = b""
        status = int(e.code)
        ctype = e.headers.get("Content-Type") if e.headers else ""
        final_url = url
    except Exception as e:
        return {
            "ok": False,
            "url": url,
            "status": None,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "bytes": 0,
            "denied": True,
            "reason": f"{type(e).__name__}: {e}",
            "snippet": "",
            "text": "",
        }

    elapsed_ms = int((time.time() - t0) * 1000)
    text = _decode_body(raw)
    low = text.lower()
    denied = False
    reason = "ok"
    if status in (401, 403, 429, 503) or status >= 400:
        denied = True
        reason = f"http_{status}"
    elif status == 200 and len(raw) < 200:
        denied = True
        reason = "body_too_small"
    else:
        for marker in _DENY_MARKERS:
            if marker in low:
                denied = True
                reason = f"marker:{marker}"
                break

    looks_like_race = any(
        s in low
        for s in (
            "race_id=",
            "shutuba",
            "race_list",
            "netkeiba",
            "horse_name",
            "umaban",
            "race_name",
        )
    )
    if status == 200 and not denied and not looks_like_race:
        denied = True
        reason = "unexpected_content"

    return {
        "ok": (not denied) and status == 200,
        "url": final_url or url,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "bytes": len(raw),
        "content_type": ctype,
        "denied": denied,
        "reason": reason,
        "snippet": re.sub(r"\s+", " ", text)[:180],
        "text": text,
    }


def _race_ids_from_cache(today_ymd: str) -> list[str]:
    root = _root()
    fp = root / "logs" / f"morning_bulk_races_{today_ymd}.pkl"
    if not fp.is_file():
        return []
    try:
        with open(fp, "rb") as f:
            data = pickle.load(f)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    ids = [str(k) for k in data.keys() if re.fullmatch(r"\d{12}", str(k) or "")]
    ids.sort()
    return ids


def _race_ids_from_list_html(html: str) -> list[str]:
    found = re.findall(r"race_id=(\d{12})", html or "")
    out: list[str] = []
    seen: set[str] = set()
    for rid in found:
        if rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


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


def _notify_ops_fallback(event: str, status: str, detail: str) -> None:
    try:
        root = _root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from ops_discord_notify import notify_action  # type: ignore

        notify_action(event, status=status, detail=detail[:300])
    except Exception:
        pass


def run_netkeiba_access_test() -> dict[str, Any]:
    """netkeiba 一覧＋出馬表へアクセスし、拒否の有無を返す。"""
    today = _today_ymd()
    checks: list[dict[str, Any]] = []

    list_url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={today}"
    list_res = _http_get(list_url)
    list_text = list_res.pop("text", "")
    list_res["name"] = "race_list"
    checks.append(list_res)

    race_ids = _race_ids_from_list_html(list_text) or _race_ids_from_cache(today)
    target_rid: str | None = race_ids[0] if race_ids else None

    if target_rid:
        shutuba_url = (
            f"https://race.netkeiba.com/race/shutuba.html?race_id={target_rid}&rf=race_list"
        )
        shutuba_res = _http_get(shutuba_url)
        shutuba_res.pop("text", None)
        shutuba_res["name"] = "shutuba"
        shutuba_res["race_id"] = target_rid
        checks.append(shutuba_res)
    else:
        top = _http_get("https://race.netkeiba.com/top/")
        top.pop("text", None)
        top["name"] = "race_top"
        checks.append(top)

    denied_any = any(bool(c.get("denied")) or not c.get("ok") for c in checks)
    overall_ok = (not denied_any) and all(c.get("status") == 200 for c in checks)

    summary: dict[str, Any] = {
        "ok": overall_ok,
        "denied": denied_any,
        "date": today,
        "race_id": target_rid,
        "checks": checks,
        "message": (
            "netkeibaへのアクセスは正常です（拒否なし）"
            if overall_ok
            else "netkeibaへのアクセスに拒否または異常を検出しました"
        ),
    }

    lines = [
        f"**netkeiba アクセス試験** {'OK' if overall_ok else 'NG'}",
        f"日付: {today}",
        f"race_id: {target_rid or '(なし)'}",
    ]
    for c in checks:
        mark = "OK" if c.get("ok") else "NG"
        lines.append(
            f"- {c.get('name')}: {mark} status={c.get('status')} "
            f"{c.get('elapsed_ms')}ms reason={c.get('reason')}"
        )
    detail = "\n".join(lines)

    webhook = _test_webhook_url()
    if webhook:
        color = 0x2ECC71 if overall_ok else 0xE74C3C
        notify = _post_discord_webhook(
            webhook,
            content="netkeiba アクセス試験の結果です",
            embeds=[
                {
                    "title": "netkeiba アクセス試験",
                    "description": detail[:3900],
                    "color": color,
                }
            ],
        )
    else:
        _notify_ops_fallback(
            "netkeiba_access_test",
            "ok" if overall_ok else "error",
            detail.replace("\n", " | ")[:300],
        )
        notify = {
            "ok": False,
            "error": "webhook_not_configured",
            "message": (
                "DISCORD_WEBHOOK_TEST（または ADMIN_TEST_WEBHOOK_URL）が未設定のため"
                " ops 通知へフォールバックしました"
            ),
        }
    summary["webhook"] = notify
    summary["webhook_configured"] = bool(webhook)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_netkeiba_access_test(), ensure_ascii=False, indent=2))

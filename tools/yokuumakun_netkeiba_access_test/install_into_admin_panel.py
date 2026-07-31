#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin_panel_api.py に netkeiba アクセス試験エンドポイントを組み込む。

使い方（サーバー上で）:
  python3 install_into_admin_panel.py /opt/yokuumakun_auto-x
  sudo systemctl restart yokuum-admin-panel.service
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

DOC_LINE = "  POST /admin/netkeiba-access-test"


def _detect_helpers(text: str) -> dict[str, str]:
    """既存 API のヘルパー名を推定する。"""
    auth = "_require_auth"
    for cand in (
        "_require_auth",
        "_auth_session",
        "_check_auth",
        "_require_session",
        "_authorize",
    ):
        if f"def {cand}(" in text:
            auth = cand
            break

    append = "_append_ops"
    for cand in (
        "_append_ops",
        "_record_ops",
        "_ops_append",
        "_log_ops",
        "_append_ops_log",
        "_write_ops",
    ):
        if f"def {cand}(" in text:
            append = cand
            break

    notify = "_notify_ops"
    if "def _notify_ops(" not in text:
        notify = ""

    json_m = "_json"
    if "def _json(" not in text:
        if "def _send_json(" in text:
            json_m = "_send_json"
        elif "def _write_json(" in text:
            json_m = "_write_json"

    client_ip = "_client_ip"
    if "def _client_ip(" not in text:
        client_ip = "lambda _h: '0.0.0.0'"

    return {
        "auth": auth,
        "append": append,
        "notify": notify,
        "json": json_m,
        "client_ip": client_ip,
    }


def _handler_method(h: dict[str, str]) -> str:
    notify_line = (
        f'        {h["notify"]}("admin_netkeiba_access_test", st, detail[:200])\n'
        if h["notify"]
        else ""
    )
    # append シグネチャはキーワード ip= を優先。無ければ位置引数にフォールバックしないよう try で包む
    return f'''
    def _handle_netkeiba_access_test(self) -> None:
        meta = self.{h["auth"]}()
        if meta is None:
            return
        try:
            ip = str((meta or {{}}).get("ip") or {h["client_ip"]}(self))
        except Exception:
            ip = ""
        try:
            from netkeiba_access_test import run_netkeiba_access_test

            result = run_netkeiba_access_test()
        except Exception as e:
            try:
                {h["append"]}(
                    "admin_netkeiba_access_test",
                    "error",
                    f"{{type(e).__name__}}: {{e}}",
                    ip=ip,
                )
            except TypeError:
                {h["append"]}(
                    "admin_netkeiba_access_test",
                    "error",
                    f"{{type(e).__name__}}: {{e}}",
                )
            self.{h["json"]}(
                500,
                {{
                    "ok": False,
                    "error": "access_test_failed",
                    "message": f"アクセス試験に失敗しました: {{type(e).__name__}}: {{e}}",
                }},
            )
            return
        st = "ok" if result.get("ok") else "error"
        detail = str(result.get("message") or "")
        wh = result.get("webhook") or {{}}
        if not result.get("webhook_configured"):
            detail += "（テスト用Webhook未設定）"
        elif not (wh.get("ok")):
            detail += f"（Webhook通知失敗: {{wh.get('error') or wh.get('status')}}）"
        else:
            detail += "（テスト用Webhookへ通知済み）"
        try:
            {h["append"]}(
                "admin_netkeiba_access_test",
                st,
                detail,
                ip=ip,
                extra={{
                    "denied": bool(result.get("denied")),
                    "race_id": result.get("race_id"),
                    "date": result.get("date"),
                }},
            )
        except TypeError:
            try:
                {h["append"]}("admin_netkeiba_access_test", st, detail, ip=ip)
            except TypeError:
                {h["append"]}("admin_netkeiba_access_test", st, detail)
{notify_line}        out = dict(result)
        out["ok"] = bool(result.get("ok"))
        self.{h["json"]}(200, out)
'''


ROUTE_SNIPPET = '''        if path == "/admin/netkeiba-access-test":
            self._handle_netkeiba_access_test()
            return
'''


def _ensure_route(text: str) -> str:
    if "/admin/netkeiba-access-test" in text and "_handle_netkeiba_access_test()" in text:
        return text
    anchors = (
        '        if path == "/admin/morning-bulk-rerun":',
        '        if path == "/admin/modem-reboot":',
        '        if path == "/admin/ops-logs":',
    )
    for a in anchors:
        if a in text:
            return text.replace(a, ROUTE_SNIPPET + a, 1)
    # フォールバック: do_POST 内の not_found 直前
    m = re.search(r'(\n\s+self\._json\(\s*404,\s*\{[^}]*not_found)', text)
    if m:
        return text[: m.start()] + "\n" + ROUTE_SNIPPET + text[m.start() :]
    raise RuntimeError("ルート挿入位置が見つかりません")


def _ensure_handler(text: str, handler: str) -> str:
    if "def _handle_netkeiba_access_test(" in text:
        # 既存ハンドラを置換
        text = re.sub(
            r"\n    def _handle_netkeiba_access_test\(self\) -> None:.*?(?=\n    def )",
            "\n" + handler.lstrip("\n"),
            text,
            count=1,
            flags=re.S,
        )
        return text
    for anchor in (
        "    def _handle_morning_bulk(self) -> None:",
        "    def _handle_modem_reboot(self) -> None:",
        "    def _handle_ops_logs(self) -> None:",
    ):
        if anchor in text:
            return text.replace(anchor, handler + "\n" + anchor, 1)
    raise RuntimeError("ハンドラ挿入位置が見つかりません")


def _ensure_doc(text: str) -> str:
    if DOC_LINE in text:
        return text
    for a in (
        "  POST /admin/morning-bulk-rerun",
        "  POST /admin/modem-reboot",
        "  GET  /admin/ops-logs",
    ):
        if a in text:
            return text.replace(a, DOC_LINE + "\n" + a, 1)
    return text


def install(root: Path) -> None:
    root = root.resolve()
    api = root / "admin_panel_api.py"
    if not api.is_file():
        raise SystemExit(f"admin_panel_api.py がありません: {api}")

    src_mod = Path(__file__).resolve().parent / "netkeiba_access_test.py"
    if not src_mod.is_file():
        raise SystemExit(f"モジュールがありません: {src_mod}")
    dst_mod = root / "netkeiba_access_test.py"
    shutil.copy2(src_mod, dst_mod)
    print(f"copied {dst_mod}")

    original = api.read_text(encoding="utf-8")
    helpers = _detect_helpers(original)
    print("helpers", helpers)
    handler = _handler_method(helpers)
    updated = _ensure_doc(original)
    updated = _ensure_route(updated)
    updated = _ensure_handler(updated, handler)
    if updated != original:
        bak = api.with_suffix(".py.bak_netkeiba_access")
        if not bak.is_file():
            bak.write_text(original, encoding="utf-8")
        api.write_text(updated, encoding="utf-8")
        print(f"patched {api}")
    else:
        print(f"no textual change for {api}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/yokuumakun_auto-x")
    install(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin_panel_api.py の _handle_morning_bulk を起動確認付き実装に差し替える。

旧挙動: 起動要求を投げてすぐ ok → UI が「完了」に見える。
新挙動: automation active + worker プロセス確認後にのみ ok。
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN admin_morning_bulk_rerun_guard"
END = "# END admin_morning_bulk_rerun_guard"


def _auth_snippet(text: str) -> str:
    if "def _require_session(" in text:
        return (
            "token, meta = self._require_session()\n"
            "        if not token or not meta:\n"
            '            code, body, ct = _json_bytes({"ok": False, "error": "unauthorized"}, 401)\n'
            "            self._send(code, body, ct)\n"
            "            return"
        )
    return (
        "meta = self._require_auth()\n"
        "        if not meta:\n"
        '            code, body, ct = _json_bytes({"ok": False, "error": "unauthorized"}, 401)\n'
        "            self._send(code, body, ct)\n"
        "            return"
    )


def _handler(auth_call: str) -> str:
    return f'''
    {BEGIN}
    def _handle_morning_bulk(self) -> None:
        {auth_call}
        try:
            from morning_bulk_rerun import start_morning_bulk_rerun

            result = start_morning_bulk_rerun(_root())
        except Exception as e:
            result = {{
                "ok": False,
                "action": "morning_bulk_rerun",
                "error": f"{{type(e).__name__}}: {{e}}",
                "message": f"一斉予想再実行で例外: {{type(e).__name__}}: {{e}}",
            }}
        try:
            ip = _client_ip(self)
        except Exception:
            ip = ""
        status = "ok" if result.get("ok") else "error"
        detail = str(result.get("message") or result)[:300]
        try:
            _append_ops("admin_panel", "admin_morning_bulk_rerun", status, detail, ip=ip)
        except TypeError:
            try:
                _append_ops("admin_panel", "admin_morning_bulk_rerun", status, detail)
            except Exception:
                pass
        except Exception:
            pass
        try:
            _notify_ops("admin_morning_bulk_rerun", status, detail[:200])
        except Exception:
            pass
        code, body, ct = _json_bytes(result, 200 if result.get("ok") else 500)
        self._send(code, body, ct)
    {END}
'''


def _strip_guard(text: str) -> str:
    return re.sub(
        rf"\n?[ \t]*{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "\n",
        text,
    )


def _strip_old_morning_bulk_method(text: str) -> str:
    """Remove existing _handle_morning_bulk method (guarded or original)."""
    return re.sub(
        r"(?m)^    def _handle_morning_bulk\(self\)[\s\S]*?(?=\n    def |\nclass |\Z)",
        "",
        text,
    )


def install(root: Path) -> None:
    root = root.resolve()
    here = Path(__file__).resolve().parent
    src = here / "morning_bulk_rerun.py"
    dst = root / "morning_bulk_rerun.py"
    if src.is_file():
        shutil.copy2(src, dst)
        print(f"installed {dst}")

    api = root / "admin_panel_api.py"
    if not api.is_file():
        raise SystemExit(f"missing {api}")

    text = api.read_text(encoding="utf-8", errors="replace")
    text = _strip_guard(text)
    text = _strip_old_morning_bulk_method(text)

    # ensure route still present
    route = (
        '        if path == "/admin/morning-bulk-rerun":\n'
        "            self._handle_morning_bulk()\n"
        "            return\n"
    )
    if "/admin/morning-bulk-rerun" not in text:
        m = re.search(r'(?m)^(?P<ind>\s*)if path == "/admin/modem-reboot":\n', text)
        if not m:
            m = re.search(
                r'(?m)^(?P<ind>\s*)if path == "/admin/publish-public-snapshot":\n',
                text,
            )
        if not m:
            raise SystemExit("route anchor not found for morning-bulk-rerun")
        text = text[: m.start()] + route + text[m.start() :]

    handler = _handler(_auth_snippet(text))
    # insert before modem reboot / publish / ops_logs handler
    inserted = False
    for anchor in (
        r"(?m)^    def _handle_modem_reboot\(self\)",
        r"(?m)^    def _handle_publish_public_snapshot\(self\)",
        r"(?m)^    def _handle_ops_logs\(self\)",
        r"(?m)^    def do_GET\(self\)",
    ):
        m = re.search(anchor, text)
        if m:
            text = text[: m.start()] + handler + "\n" + text[m.start() :]
            inserted = True
            break
    if not inserted:
        # append near end of class — before last top-level def outside class is hard;
        # fall back: before if __name__
        m = re.search(r"(?m)^if __name__ == ", text)
        if not m:
            raise SystemExit("handler insert anchor not found")
        text = text[: m.start()] + handler + "\n" + text[m.start() :]

    bak = api.with_suffix(api.suffix + ".bak_morning_bulk_rerun_guard")
    if not bak.exists():
        shutil.copy2(api, bak)
        print(f"backup {bak}")
    api.write_text(text, encoding="utf-8")
    print(f"patched {api}")


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x")
    install(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

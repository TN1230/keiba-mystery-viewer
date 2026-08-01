#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin_panel_api.py に POST /admin/publish-public-snapshot を追加する。"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN admin_publish_public_snapshot"
END = "# END admin_publish_public_snapshot"
DOC_LINE = "  POST /admin/publish-public-snapshot"


def _handler(auth_call: str) -> str:
    return f'''
    {BEGIN}
    def _handle_publish_public_snapshot(self) -> None:
        {auth_call}
        try:
            from force_publish_public_snapshot import run_publish

            result = run_publish(force=True)
        except Exception as e:
            result = {{"ok": False, "error": f"{{type(e).__name__}}: {{e}}"}}
        try:
            ip = _client_ip(self)
        except Exception:
            ip = ""
        try:
            _append_ops(
                "admin_panel",
                "admin_publish_public_snapshot",
                "ok" if result.get("ok") else "error",
                str(result)[:300],
                ip=ip,
            )
        except TypeError:
            try:
                _append_ops(
                    "admin_panel",
                    "admin_publish_public_snapshot",
                    "ok" if result.get("ok") else "error",
                    str(result)[:300],
                )
            except Exception:
                pass
        except Exception:
            pass
        try:
            _notify_ops(
                "admin_publish_public_snapshot",
                "ok" if result.get("ok") else "error",
                str(result)[:200],
            )
        except Exception:
            pass
        code, body, ct = _json_bytes(result, 200 if result.get("ok") else 500)
        self._send(code, body, ct)
    {END}
'''


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


def _strip(text: str) -> str:
    return re.sub(
        rf"\n?[ \t]*{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "\n",
        text,
    )


def install(root: Path) -> None:
    root = root.resolve()
    src = Path(__file__).resolve().parent / "force_publish_public_snapshot.py"
    dst = root / "force_publish_public_snapshot.py"
    if src.is_file() and src.resolve() != dst.resolve():
        shutil.copy2(src, dst)

    api = root / "admin_panel_api.py"
    if not api.is_file():
        raise SystemExit(f"missing {api}")

    text = api.read_text(encoding="utf-8", errors="replace")
    text = _strip(text)

    if DOC_LINE not in text:
        text = re.sub(
            r"(POST /admin/modem-reboot\n)",
            r"\1" + DOC_LINE + "\n",
            text,
            count=1,
        )
        if DOC_LINE not in text:
            text = re.sub(
                r"(POST /admin/morning-bulk-rerun\n)",
                r"\1" + DOC_LINE + "\n",
                text,
                count=1,
            )

    # ルーティング
    route = (
        '        if path == "/admin/publish-public-snapshot":\n'
        "            self._handle_publish_public_snapshot()\n"
        "            return\n"
    )
    if "/admin/publish-public-snapshot" not in text:
        m = re.search(
            r'(?m)^(?P<ind>\s*)if path == "/admin/modem-reboot":\n',
            text,
        )
        if m:
            text = text[: m.start()] + route + text[m.start() :]
        else:
            m = re.search(
                r'(?m)^(?P<ind>\s*)if path == "/admin/morning-bulk-rerun":\n'
                r"[\s\S]*?return\n",
                text,
            )
            if not m:
                raise SystemExit("route anchor not found")
            text = text[: m.end()] + route + text[m.end() :]

    # ハンドラ本体（_handle_modem_reboot の前、またはクラス末尾付近）
    if "_handle_publish_public_snapshot" not in text:
        handler = _handler(_auth_snippet(text))
        m = re.search(r"(?m)^    def _handle_modem_reboot\(self\)", text)
        if m:
            text = text[: m.start()] + handler + "\n" + text[m.start() :]
        else:
            m = re.search(r"(?m)^    def _handle_morning_bulk\(self\)[\s\S]*?(?=\n    def )", text)
            if not m:
                raise SystemExit("handler anchor not found")
            text = text[: m.end()] + "\n" + handler + text[m.end() :]

    bak = api.with_suffix(api.suffix + ".bak_publish_endpoint")
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

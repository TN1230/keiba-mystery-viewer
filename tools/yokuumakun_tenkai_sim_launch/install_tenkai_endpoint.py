#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin_panel_api.py に GET /tenkai を組み込む（TEMP: TENKAI_SIM_LAUNCH）。"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN TEMP: TENKAI_SIM_LAUNCH"
END = "# END TEMP: TENKAI_SIM_LAUNCH"
DOC_LINE = "  GET  /tenkai                 ?race_id=&place=&R=&schedule_date=  (一時)"


HANDLER = f'''
    {BEGIN}
    def _handle_tenkai_sim(self) -> None:
        try:
            from urllib.parse import urlparse
            from tenkai_sim_gateway import params_from_query, render_html

            parsed = urlparse(self.path)
            params = params_from_query(parsed.query or "")
            code, body, ct = render_html(params)
        except Exception as e:
            msg = f"tenkai gateway error: {{type(e).__name__}}: {{e}}"
            body = msg.encode("utf-8")
            code, ct = 500, "text/plain; charset=utf-8"
        try:
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # 別タブ表示用。管理APIの CORS 設定に依存せず読めるようにする
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass
    {END}
'''

def _strip(text: str) -> str:
    text = re.sub(
        rf"\n?[ \t]*{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "\n",
        text,
    )
    # 旧ルート残骸
    text = re.sub(
        r"\n[ \t]*if path == \"/tenkai\"[^\n]*\n[ \t]*self\._handle_tenkai_sim\(\)\n[ \t]*return\n",
        "\n",
        text,
    )
    return text


def _ensure_handler(text: str) -> str:
    if "def _handle_tenkai_sim(" in text:
        return text
    handler = HANDLER
    if not handler.endswith("\n"):
        handler += "\n"
    for anchor in (
        "    def do_GET(self)",
        "    def do_POST(self)",
        "    def _handle_morning_bulk(self)",
        "    def _handle_ops_logs(self)",
    ):
        if anchor in text:
            return text.replace(anchor, handler + "\n" + anchor, 1)
    raise RuntimeError("handler insert anchor not found")


def _ensure_get_route(text: str) -> str:
    if "/tenkai" in text and "_handle_tenkai_sim()" in text and BEGIN in text:
        # 既に TEMP ブロック付きならOK
        if "path == \"/tenkai\"" in text or 'path.startswith("/tenkai?")' in text:
            return text
    # do_GET 内の path 正規化直後へ挿入
    m = re.search(
        r"(def do_GET\(self\)[^\n]*:\n(?:.*\n)*?)"
        r"([ \t]+)(path\s*=\s*.*\n)",
        text,
    )
    if m:
        ind = m.group(2)
        route = (
            f"{ind}{BEGIN}\n"
            f"{ind}if path == \"/tenkai\" or path.startswith(\"/tenkai?\"):\n"
            f"{ind}    self._handle_tenkai_sim()\n"
            f"{ind}    return\n"
            f"{ind}{END}\n"
        )
        # path 代入の後に入れる
        insert_at = m.end()
        return text[:insert_at] + route + text[insert_at:]

    # フォールバック: /health の前
    for pat in (
        r'([ \t]+)if path == "/health":\n',
        r'([ \t]+)if path in \("/health", "/":\):\n',
        r'([ \t]+)if path == "/":\n',
    ):
        m = re.search(pat, text)
        if m:
            ind = m.group(1)
            route = (
                f"{ind}{BEGIN}\n"
                f"{ind}if path == \"/tenkai\" or path.startswith(\"/tenkai?\"):\n"
                f"{ind}    self._handle_tenkai_sim()\n"
                f"{ind}    return\n"
                f"{ind}{END}\n"
            )
            return text[: m.start()] + route + text[m.start() :]
    raise RuntimeError("GET route insert anchor not found")


def _ensure_doc(text: str) -> str:
    if DOC_LINE in text:
        return text
    for a in (
        "  GET  /health\n",
        "  POST /admin/login\n",
        "  POST /admin/morning-bulk-rerun\n",
    ):
        if a in text:
            return text.replace(a, a + DOC_LINE + "\n", 1)
    return text


def install(root: Path) -> None:
    target = root / "admin_panel_api.py"
    if not target.is_file():
        raise SystemExit(f"missing {target}")

    gw_src = Path(__file__).resolve().parent / "tenkai_sim_gateway.py"
    if gw_src.is_file():
        shutil.copy2(gw_src, root / "tenkai_sim_gateway.py")

    bak = root / "admin_panel_api.py.bak_tenkai_sim"
    if not bak.is_file():
        shutil.copy2(target, bak)

    text = target.read_text(encoding="utf-8")
    text = _strip(text)
    text = _ensure_handler(text)
    text = _ensure_get_route(text)
    text = _ensure_doc(text)
    target.write_text(text, encoding="utf-8")
    print(f"patched {target}")
    print(f"gateway -> {root / 'tenkai_sim_gateway.py'}")


def uninstall(root: Path) -> None:
    target = root / "admin_panel_api.py"
    if not target.is_file():
        raise SystemExit(f"missing {target}")
    text = _strip(target.read_text(encoding="utf-8"))
    text = text.replace(DOC_LINE + "\n", "")
    target.write_text(text, encoding="utf-8")
    print(f"unpatched {target}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="/opt/yokuumakun_auto-x")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if args.uninstall:
        uninstall(root)
    else:
        install(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

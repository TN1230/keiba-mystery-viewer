#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin_panel_api.py に POST /admin/remote-bootstrap を追加する。

許可された固定アクションのみ（任意シェルは不可）:
  - force_publish
  - restart_ssh_tunnel
  - ensure_ssh_tunnel  (embedded bootstrap を実行)
"""

from __future__ import annotations

import re
import shutil
import sys
import textwrap
from pathlib import Path

BEGIN = "# BEGIN admin_remote_bootstrap"
END = "# END admin_remote_bootstrap"
DOC_LINE = "  POST /admin/remote-bootstrap"


def _handler_block(use_session: bool) -> str:
    if use_session:
        auth = textwrap.dedent(
            """\
            token, meta = self._require_session()
            if not token or not meta:
                code, body, ct = _json_bytes({"ok": False, "error": "unauthorized"}, 401)
                self._send(code, body, ct)
                return
            """
        )
    else:
        auth = textwrap.dedent(
            """\
            meta = self._require_auth()
            if not meta:
                code, body, ct = _json_bytes({"ok": False, "error": "unauthorized"}, 401)
                self._send(code, body, ct)
                return
            """
        )
    body = textwrap.dedent(
        f"""\
        {BEGIN}
        def _handle_remote_bootstrap(self) -> None:
        {{AUTH}}
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except Exception:
                length = 0
            raw = self.rfile.read(length) if length > 0 else b"{{}}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{{}}")
            except Exception:
                payload = {{}}
            action = str((payload or {{}}).get("action") or "").strip()
            root = _root()
            py = _py()
            result: dict[str, Any] = {{"ok": False, "action": action}}
            try:
                if action == "force_publish":
                    from force_publish_public_snapshot import run_publish
                    result = run_publish(force=True)
                    result["action"] = action
                elif action == "restart_ssh_tunnel":
                    cp = subprocess.run(
                        ["systemctl", "restart", "yokuum-ssh-tcp-tunnel.service"],
                        capture_output=True, text=True, timeout=60,
                    )
                    result = {{
                        "ok": cp.returncode == 0,
                        "action": action,
                        "stdout": (cp.stdout or "")[-500:],
                        "stderr": (cp.stderr or "")[-500:],
                    }}
                elif action == "ensure_ssh_tunnel":
                    script = (
                        "curl -fsSL https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@"
                        "cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_lan_apply_pending/"
                        "bootstrap_tunnel_embedded.sh | bash"
                    )
                    cp = subprocess.run(
                        ["bash", "-lc", script],
                        cwd=str(root),
                        capture_output=True, text=True, timeout=300,
                        env={{**os.environ, "YOKUMAKUN_ROOT": str(root)}},
                    )
                    result = {{
                        "ok": cp.returncode == 0,
                        "action": action,
                        "stdout": (cp.stdout or "")[-1500:],
                        "stderr": (cp.stderr or "")[-800:],
                    }}
                else:
                    result = {{
                        "ok": False,
                        "error": "unknown_action",
                        "allowed": ["force_publish", "restart_ssh_tunnel", "ensure_ssh_tunnel"],
                    }}
            except Exception as e:
                result = {{"ok": False, "action": action, "error": f"{{type(e).__name__}}: {{e}}"}}
            try:
                ip = _client_ip(self)
            except Exception:
                ip = ""
            try:
                _append_ops("admin_panel", "admin_remote_bootstrap", "ok" if result.get("ok") else "error", str(result)[:300], ip=ip)
            except TypeError:
                try:
                    _append_ops("admin_panel", "admin_remote_bootstrap", "ok" if result.get("ok") else "error", str(result)[:300])
                except Exception:
                    pass
            except Exception:
                pass
            code, body, ct = _json_bytes(result, 200 if result.get("ok") else 500)
            self._send(code, body, ct)
        {END}
        """
    )
    # indent auth (4 spaces relative to method body already in block as 4 spaces under def)
    auth_indented = textwrap.indent(auth, "    ")
    # whole block is class-level (4 spaces)
    block = body.replace("{AUTH}", auth_indented.rstrip())
    return textwrap.indent(textwrap.dedent(block), "    ")


def _strip(text: str) -> str:
    return re.sub(
        rf"\n?[ \t]*{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "\n",
        text,
    )


def _strip_route(text: str) -> str:
    return re.sub(
        r"\n[ \t]*if path == \"/admin/remote-bootstrap\":\n"
        r"[ \t]*self\._handle_remote_bootstrap\(\)\n"
        r"[ \t]*return\n",
        "\n",
        text,
    )


def install(root: Path) -> None:
    target = root / "admin_panel_api.py"
    if not target.is_file():
        raise SystemExit(f"missing {target}")
    text = target.read_text(encoding="utf-8")
    text = _strip(text)
    text = _strip_route(text)

    if "import subprocess" not in text:
        text = text.replace("import sys\n", "import sys\nimport subprocess\n", 1)

    use_session = "def _require_session(" in text
    handler = _handler_block(use_session)
    if not handler.endswith("\n"):
        handler += "\n"

    if "_handle_publish_public_snapshot" in text:
        m = re.search(r"(?m)^    def _handle_publish_public_snapshot\(self\)", text)
        if not m:
            raise SystemExit("publish handler found by name but not at class indent")
        text = text[: m.start()] + handler + "\n" + text[m.start() :]
    else:
        m = re.search(r"(?m)^    def do_POST\(self\)", text)
        if not m:
            raise SystemExit("do_POST not found")
        text = text[: m.start()] + handler + "\n" + text[m.start() :]

    if "/admin/remote-bootstrap" not in text:
        route = (
            '        if path == "/admin/remote-bootstrap":\n'
            "            self._handle_remote_bootstrap()\n"
            "            return\n"
        )
        m = None
        for pat in (
            r'(?m)^(?P<ind>\s*)if path == "/admin/publish-public-snapshot":\n',
            r'(?m)^(?P<ind>\s*)if path == "/admin/morning-bulk-rerun":\n',
            r'(?m)^(?P<ind>\s*)if path == "/admin/modem-reboot":\n',
        ):
            m = re.search(pat, text)
            if m:
                break
        if not m:
            raise SystemExit("no route anchor")
        text = text[: m.start()] + route + text[m.start() :]

    if DOC_LINE not in text:
        text = text.replace(
            "  POST /admin/morning-bulk-rerun\n",
            "  POST /admin/morning-bulk-rerun\n" + DOC_LINE + "\n",
            1,
        )

    bak = target.with_suffix(".py.bak_remote_bootstrap")
    if not bak.exists():
        shutil.copy2(target, bak)
    target.write_text(text, encoding="utf-8")
    print(f"installed remote-bootstrap into {target} (backup {bak})")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/yokuumakun_auto-x").resolve()
    install(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

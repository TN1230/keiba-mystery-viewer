#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from install_publish_endpoint import DOC_LINE, install  # noqa: E402
from patch_worker_publish_on_success import BEGIN, patch  # noqa: E402


class PatchWorkerTests(unittest.TestCase):
    def test_injects_after_mark_done(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "morning_bulk_server_worker.py").write_text(
                "def main():\n"
                "    if quality.get('ok'):\n"
                "        _mark_morning_bulk_done_on_disk(state_day, slot)\n"
                "        _log(f\"done ok n_ok={n_ok}\")\n"
                "        try:\n"
                "            from ops_discord_notify import notify_action\n"
                "        except Exception:\n"
                "            pass\n"
                "        return 0\n",
                encoding="utf-8",
            )
            # force_publish source must exist beside patcher
            patch(root)
            text = (root / "morning_bulk_server_worker.py").read_text(encoding="utf-8")
            self.assertIn(BEGIN, text)
            self.assertIn("publishing public viewer snapshot after quality ok", text)
            i_mark = text.index("_mark_morning_bulk_done_on_disk")
            i_pub = text.index(BEGIN)
            i_notify = text.index("ops_discord_notify")
            self.assertLess(i_mark, i_pub)
            self.assertLess(i_pub, i_notify)
            # mark done と同じインデント
            for line in text.splitlines():
                if BEGIN in line:
                    self.assertTrue(line.startswith("        # BEGIN"))
                    break
            else:
                self.fail("BEGIN line missing")


class InstallEndpointTests(unittest.TestCase):
    def test_adds_route_and_handler(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "admin_panel_api.py").write_text(
                '"""doc\n'
                "  POST /admin/morning-bulk-rerun\n"
                "  POST /admin/modem-reboot\n"
                '"""\n'
                "def _json_bytes(obj, code=200):\n"
                "    return code, b'{}', 'application/json'\n"
                "def _client_ip(h):\n"
                "    return '1.2.3.4'\n"
                "def _append_ops(*a, **k):\n"
                "    pass\n"
                "def _notify_ops(*a, **k):\n"
                "    pass\n"
                "class H:\n"
                "    def _require_session(self):\n"
                "        return 't', {'ip': '1.2.3.4'}\n"
                "    def _send(self, *a):\n"
                "        pass\n"
                "    def do_POST(self):\n"
                '        path = "/admin/morning-bulk-rerun"\n'
                '        if path == "/admin/morning-bulk-rerun":\n'
                "            self._handle_morning_bulk()\n"
                "            return\n"
                '        if path == "/admin/modem-reboot":\n'
                "            self._handle_modem_reboot()\n"
                "            return\n"
                "    def _handle_morning_bulk(self):\n"
                "        pass\n"
                "    def _handle_modem_reboot(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            install(root)
            text = (root / "admin_panel_api.py").read_text(encoding="utf-8")
            self.assertIn(DOC_LINE, text)
            self.assertIn("/admin/publish-public-snapshot", text)
            self.assertIn("_handle_publish_public_snapshot", text)
            self.assertTrue((root / "force_publish_public_snapshot.py").is_file())


if __name__ == "__main__":
    unittest.main()

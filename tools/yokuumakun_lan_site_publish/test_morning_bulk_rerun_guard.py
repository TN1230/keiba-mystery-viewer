#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class MorningBulkRerunLogicTest(unittest.TestCase):
    def test_clears_done_flags_before_spawn(self):
        import morning_bulk_rerun as m

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            flag = logs / "morning_bulk_done_2026-08-02.flag"
            flag.write_text("ok", encoding="utf-8")
            (root / "morning_bulk_server_worker.py").write_text("# stub\n", encoding="utf-8")
            with mock.patch.object(m, "_today_jst", return_value="2026-08-02"):
                with mock.patch.object(m, "stop_existing_workers", return_value=[]):
                    with mock.patch.object(
                        m, "ensure_automation_active", return_value=(True, "automation=active")
                    ):
                        with mock.patch.object(
                            m, "start_worker", return_value=(True, "spawned pid=9", 9)
                        ):
                            with mock.patch.object(
                                m, "wait_worker_running", return_value=(True, [9])
                            ):
                                out = m.start_morning_bulk_rerun(root, verify_sec=1)
        self.assertTrue(out["ok"])
        self.assertIn("morning_bulk_done_2026-08-02.flag", out.get("cleared_flags") or [])
        self.assertFalse(flag.exists())

    def test_fails_when_automation_stays_inactive(self):
        import morning_bulk_rerun as m

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "morning_bulk_server_worker.py").write_text("# stub\n", encoding="utf-8")
            with mock.patch.object(m, "stop_existing_workers", return_value=[]):
                with mock.patch.object(m, "clear_morning_bulk_flags", return_value=[]):
                    with mock.patch.object(
                        m, "ensure_automation_active", return_value=(False, "automation=inactive")
                    ):
                        out = m.start_morning_bulk_rerun(root)
        self.assertFalse(out["ok"])
        self.assertEqual(out.get("error"), "automation_inactive")

    def test_ok_when_worker_observed(self):
        import morning_bulk_rerun as m

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "morning_bulk_server_worker.py").write_text("# stub\n", encoding="utf-8")
            with mock.patch.object(m, "stop_existing_workers", return_value=[]):
                with mock.patch.object(m, "clear_morning_bulk_flags", return_value=[]):
                    with mock.patch.object(
                        m, "ensure_automation_active", return_value=(True, "automation=active")
                    ):
                        with mock.patch.object(
                            m, "start_worker", return_value=(True, "spawned pid=9", 9)
                        ):
                            with mock.patch.object(
                                m, "wait_worker_running", return_value=(True, [9])
                            ):
                                out = m.start_morning_bulk_rerun(root, verify_sec=1)
        self.assertTrue(out["ok"])
        self.assertTrue(out["worker_running"])
        self.assertIn("起動しました", out["message"])
        self.assertIn("起動確認済み", out["message"])

class InstallGuardTest(unittest.TestCase):
    def test_replaces_handler_and_keeps_route(self):
        import install_morning_bulk_rerun_guard as inst

        sample = '''
class H:
    def do_POST(self):
        path = "/admin/x"
        if path == "/admin/morning-bulk-rerun":
            self._handle_morning_bulk()
            return
        if path == "/admin/modem-reboot":
            self._handle_modem_reboot()
            return

    def _require_session(self):
        return "t", {}

    def _handle_morning_bulk(self) -> None:
        # old: always ok
        code, body, ct = _json_bytes({"ok": True, "message": "started"}, 200)
        self._send(code, body, ct)

    def _handle_modem_reboot(self) -> None:
        pass
'''
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "admin_panel_api.py").write_text(sample, encoding="utf-8")
            # copy module next to installer expectations
            src = Path(inst.__file__).resolve().parent / "morning_bulk_rerun.py"
            self.assertTrue(src.is_file())
            inst.install(root)
            text = (root / "admin_panel_api.py").read_text(encoding="utf-8")
            self.assertIn("BEGIN admin_morning_bulk_rerun_guard", text)
            self.assertIn("start_morning_bulk_rerun", text)
            self.assertIn('/admin/morning-bulk-rerun', text)
            self.assertEqual(text.count("def _handle_morning_bulk"), 1)
            self.assertNotIn('"message": "started"', text)


if __name__ == "__main__":
    unittest.main()

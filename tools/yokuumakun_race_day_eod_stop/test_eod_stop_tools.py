#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patch_automation_jst_eod_guard import BEGIN, already_patched, patch, patch_text
from patch_race_day_stop_sudo_sys import patch_text as patch_stop_text


SAMPLE_AUTOMATION = '''\
def _tick() -> None:
    os.environ.setdefault("HWM_SERVER_AUTO", "1")

    if not _hwm_server_auto_mode_enabled():
        return

    schedule_day = effective_schedule_date_iso()
    if not _today_is_scheduled_race_day():
        return
'''

SAMPLE_STOP = '''\
#!/usr/bin/env bash
set -euo pipefail

export TZ=Asia/Tokyo

ROOT=/opt/yokuumakun_auto-x
SERVICE_NAME=yokuum-server-automation-x.service

if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  sudo systemctl stop "$SERVICE_NAME"
fi
'''


class AutomationGuardTests(unittest.TestCase):
    def test_injects_jst_guard(self) -> None:
        new, status = patch_text(SAMPLE_AUTOMATION)
        self.assertEqual(status, "patched")
        self.assertTrue(already_patched(new))
        self.assertIn('_ZI_eod("Asia/Tokyo")', new)
        self.assertIn("hour) >= 20", new)
        self.assertIn("SystemExit", new)
        # still after mode-enabled check
        self.assertLess(
            new.index("if not _hwm_server_auto_mode_enabled()"),
            new.index(BEGIN),
        )

    def test_idempotent(self) -> None:
        once, _ = patch_text(SAMPLE_AUTOMATION)
        twice, status = patch_text(once)
        self.assertEqual(status, "already")
        self.assertEqual(once.count(BEGIN), 1)
        self.assertEqual(twice.count(BEGIN), 1)

    def test_patch_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "hwm_server_automation.py").write_text(SAMPLE_AUTOMATION, encoding="utf-8")
            out = patch(root)
            self.assertTrue(out["ok"])
            text = (root / "hwm_server_automation.py").read_text(encoding="utf-8")
            self.assertIn(BEGIN, text)


class StopSudoTests(unittest.TestCase):
    def test_replaces_sudo_systemctl(self) -> None:
        new, status = patch_stop_text(SAMPLE_STOP)
        self.assertEqual(status, "patched")
        self.assertIn("sudo_sys()", new)
        self.assertIn("sudo_sys systemctl stop", new)
        self.assertNotIn("\nsudo systemctl stop", new)

    def test_idempotent_stop(self) -> None:
        once, _ = patch_stop_text(SAMPLE_STOP)
        twice, status = patch_stop_text(once)
        self.assertEqual(status, "already")


if __name__ == "__main__":
    unittest.main()

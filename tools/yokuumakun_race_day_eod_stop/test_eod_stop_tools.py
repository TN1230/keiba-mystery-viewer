#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patch_automation_jst_eod_guard import BEGIN, already_patched, patch, patch_text
from patch_race_day_stop_sudo_sys import BEGIN_ENV, BEGIN_SUDO
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

ROOT="${YOKUMAKUN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
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
    def test_replaces_sudo_and_loads_env(self) -> None:
        from patch_race_day_stop_sudo_sys import BEGIN_CLEAR

        sample = SAMPLE_STOP + '\nlog "DONE race_day_stop_hwm"\n'
        new, status = patch_stop_text(sample)
        self.assertEqual(status, "patched")
        self.assertIn(BEGIN_SUDO, new)
        self.assertIn(BEGIN_ENV, new)
        self.assertIn(BEGIN_CLEAR, new)
        self.assertIn("sudo_sys systemctl stop", new)
        self.assertIn("clear_latest_public_snapshot.py", new)
        self.assertIn('${ROOT}/.env', new)
        self.assertNotRegex(new, r"(?m)^\s*sudo systemctl stop ")

    def test_idempotent_stop(self) -> None:
        once, _ = patch_stop_text(SAMPLE_STOP)
        twice, status = patch_stop_text(once)
        self.assertEqual(status, "already")
        self.assertEqual(once.count(BEGIN_ENV), 1)


class TimerUnitTests(unittest.TestCase):
    def test_timer_is_jst_20(self) -> None:
        here = Path(__file__).resolve().parent
        tmr = (here / "yokuum-race-day-stop.timer.example").read_text(encoding="utf-8")
        self.assertIn("20:00:00 Asia/Tokyo", tmr)
        self.assertIn("Persistent=true", tmr)
        svc = (here / "yokuum-race-day-stop.service.example").read_text(encoding="utf-8")
        self.assertIn("race_day_stop_hwm.sh", svc)
        self.assertIn("TZ=Asia/Tokyo", svc)


if __name__ == "__main__":
    unittest.main()

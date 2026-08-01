#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from unittest import mock

import race_day_evening_functional_test as m


class TimetableChecksTest(unittest.TestCase):
    def test_start_schedule_armed_timer(self):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["systemctl", "is-enabled", "yokuum-race-day-start.timer"]:
                return 0, "enabled\n"
            if cmd[:3] == ["systemctl", "is-active", "yokuum-race-day-start.timer"]:
                return 0, "active\n"
            if cmd[:3] == ["systemctl", "is-enabled", "yokuum-race-day-start-guard.timer"]:
                return 0, "enabled\n"
            return 1, "inactive\n"

        with mock.patch.object(m, "_run_cmd", side_effect=fake_run), mock.patch.object(
            m, "_crontab_text", return_value="CRON_TZ=Asia/Tokyo\n"
        ):
            ok, detail, sev = m.check_start_schedule_armed()
        self.assertTrue(ok)
        self.assertIn("start.timer", detail)

    def test_evening_schedule_requires_cron_tz(self):
        with mock.patch.object(
            m, "_crontab_text", return_value="0 21 * * * race_day_evening_functional_test.py\n"
        ):
            ok, detail, sev = m.check_evening_schedule_armed()
        self.assertFalse(ok)
        self.assertIn("CRON_TZ", detail)

    def test_weekend_is_race_day_heuristic(self):
        # 2026-08-02 is Sunday
        root = mock.Mock()
        # Path behavior: use tmp via real Path in _is_race_day — call with monkeypatched helpers
        with mock.patch.object(m, "_http_get_json", return_value=(None, "x")):
            # Use a temp dir without artifacts
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as td:
                ok, why = m._is_race_day(Path(td), "2026-08-02")
        self.assertTrue(ok)
        self.assertIn("weekend", why)


if __name__ == "__main__":
    unittest.main()

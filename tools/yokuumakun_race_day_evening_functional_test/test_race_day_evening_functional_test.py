#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from race_day_evening_functional_test import (
    AutofixResult,
    CheckResult,
    NON_AUTOFIXABLE_CHECKS,
    SuiteResult,
    _autofix_enabled,
    _error_webhook_url,
    _is_race_day,
    _rebuild_bugs_warnings,
    _report_has_errors,
    attempt_autofixes,
    build_report,
)


class RaceDayGateTests(unittest.TestCase):
    def test_morning_cache_marks_race_day(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            (logs / "morning_bulk_races_20260801.pkl").write_bytes(b"x")
            ok, why = _is_race_day(root, "2026-08-01")
            self.assertTrue(ok)
            self.assertIn("cache:", why)

    def test_eod_archive_marks_race_day(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch = root / "data" / "eod_archives"
            arch.mkdir(parents=True)
            (arch / "2026-08-01.json").write_text('{"race_count": 12}', encoding="utf-8")
            ok, why = _is_race_day(root, "2026-08-01")
            self.assertTrue(ok)
            self.assertIn("eod_archive:", why)

    def test_no_evidence_is_not_race_day(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir()
            with mock.patch(
                "race_day_evening_functional_test._http_get_json",
                return_value=(None, "offline"),
            ):
                ok, why = _is_race_day(root, "2026-08-01")
            self.assertFalse(ok)
            self.assertIn("no_cache", why)


class ReportTests(unittest.TestCase):
    def test_ok_title_no_bugs(self) -> None:
        suite = SuiteResult(
            day="2026-08-01",
            started_at="2026-08-01T21:00:00+09:00",
            finished_at="2026-08-01T21:01:00+09:00",
            race_day=True,
            overall_ok=True,
            checks=[CheckResult("admin_health", True, "ok", "info", 10)],
        )
        title, desc, color = build_report(suite)
        self.assertIn("不具合無し", title)
        self.assertIn("不具合無し", desc)
        self.assertEqual(color, 0x2ECC71)

    def test_bug_title_lists_points(self) -> None:
        suite = SuiteResult(
            day="2026-08-01",
            started_at="2026-08-01T21:00:00+09:00",
            finished_at="2026-08-01T21:01:00+09:00",
            race_day=True,
            overall_ok=False,
            bugs=["automation_stopped: still active"],
            checks=[
                CheckResult(
                    "automation_stopped",
                    False,
                    "still active",
                    "error",
                    5,
                )
            ],
        )
        title, desc, color = build_report(suite)
        self.assertIn("不具合あり", title)
        self.assertIn("【不具合発生点】", desc)
        self.assertIn("automation_stopped", desc)
        self.assertEqual(color, 0xE74C3C)

    def test_skip_title(self) -> None:
        suite = SuiteResult(
            day="2026-08-03",
            started_at="2026-08-03T21:00:00+09:00",
            finished_at="2026-08-03T21:00:01+09:00",
            skipped=True,
            overall_ok=True,
        )
        title, desc, _ = build_report(suite)
        self.assertIn("スキップ", title)
        self.assertIn("開催日ではない", desc)


class ErrorWebhookRoutingTests(unittest.TestCase):
    def test_report_has_errors_on_bugs(self) -> None:
        suite = SuiteResult(
            day="2026-08-01",
            started_at="t0",
            overall_ok=False,
            bugs=["x"],
        )
        self.assertTrue(_report_has_errors(suite))

    def test_report_has_errors_false_when_ok(self) -> None:
        suite = SuiteResult(
            day="2026-08-01",
            started_at="t0",
            overall_ok=True,
        )
        self.assertFalse(_report_has_errors(suite))

    def test_skip_is_not_error_report(self) -> None:
        suite = SuiteResult(
            day="2026-08-03",
            started_at="t0",
            skipped=True,
            overall_ok=True,
        )
        self.assertFalse(_report_has_errors(suite))

    def test_error_webhook_prefers_failure_env(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "DISCORD_WEBHOOK_FAILURE": "https://example.test/failure",
                "DISCORD_WEBHOOK_URL_3": "https://example.test/url3",
            },
            clear=False,
        ):
            self.assertEqual(_error_webhook_url(), "https://example.test/failure")


class AutofixTests(unittest.TestCase):
    def test_autofix_enabled_default_on(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("YOKUMAKUN_EOD_TEST_AUTOFIX", None)
            self.assertTrue(_autofix_enabled())

    def test_autofix_disabled_by_env(self) -> None:
        with mock.patch.dict("os.environ", {"YOKUMAKUN_EOD_TEST_AUTOFIX": "0"}):
            self.assertFalse(_autofix_enabled())

    def test_non_autofixable_skipped(self) -> None:
        from race_day_evening_functional_test import Deadline

        failed = [
            CheckResult("morning_bulk_cache", False, "missing", "error"),
            CheckResult("netkeiba_light", False, "down", "error"),
        ]
        results = attempt_autofixes(
            Path("/tmp"),
            "2026-08-01",
            failed,
            deadline=Deadline(3600),
        )
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].attempted)
        self.assertEqual(results[0].skipped_reason, "non_autofixable")
        self.assertIn("morning_bulk_cache", NON_AUTOFIXABLE_CHECKS)

    def test_automation_autofix_stops_service(self) -> None:
        from race_day_evening_functional_test import Deadline, autofix_automation_stopped

        with mock.patch(
            "race_day_evening_functional_test._sudo_cmd",
            return_value=(0, ""),
        ), mock.patch(
            "race_day_evening_functional_test._run_cmd",
            return_value=(3, "inactive"),
        ):
            af = autofix_automation_stopped(Path("/tmp"), "2026-08-01")
        self.assertTrue(af.attempted)
        self.assertTrue(af.ok)
        self.assertEqual(af.check_name, "automation_stopped")

    def test_report_includes_autofix_section(self) -> None:
        suite = SuiteResult(
            day="2026-08-01",
            started_at="t0",
            finished_at="t1",
            race_day=True,
            overall_ok=True,
            autofix_recovered=True,
            initial_bugs=["automation_stopped: still active"],
            checks=[CheckResult("automation_stopped", True, "inactive", "info")],
            autofixes=[
                AutofixResult("automation_stopped", True, True, "stopped"),
            ],
        )
        title, desc, color = build_report(suite)
        self.assertIn("自己修正済", title)
        self.assertIn("【自己修正】", desc)
        self.assertIn("[FIXED] automation_stopped", desc)
        self.assertEqual(color, 0x2ECC71)

    def test_rebuild_bugs_warnings(self) -> None:
        suite = SuiteResult(
            day="2026-08-01",
            started_at="t0",
            checks=[
                CheckResult("a", False, "x", "error"),
                CheckResult("b", False, "y", "warn"),
                CheckResult("c", True, "z", "info"),
            ],
        )
        _rebuild_bugs_warnings(suite)
        self.assertEqual(suite.bugs, ["a: x"])
        self.assertEqual(suite.warnings, ["b: y"])


if __name__ == "__main__":
    unittest.main()

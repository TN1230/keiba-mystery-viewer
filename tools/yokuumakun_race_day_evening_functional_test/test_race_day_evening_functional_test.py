#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from race_day_evening_functional_test import (
    CheckResult,
    SuiteResult,
    _error_webhook_url,
    _is_race_day,
    _report_has_errors,
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


if __name__ == "__main__":
    unittest.main()

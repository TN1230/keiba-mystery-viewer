#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from clear_latest_public_snapshot import build_cleared_snapshot


class ClearLatestTests(unittest.TestCase):
    def test_build_cleared_snapshot(self) -> None:
        snap = build_cleared_snapshot("2026-08-01")
        self.assertTrue(snap["cleared"] is True)
        self.assertEqual(snap["race_count"], 0)
        self.assertEqual(snap["venues"], [])
        self.assertEqual(snap["schedule_date"], "2026-08-01")
        self.assertEqual(snap["schema_version"], 3)

    def test_preserves_timing_from_prev(self) -> None:
        prev = {
            "pre_race_trigger_mode": "6_8",
            "update_timing_pre_race_line": "・発走6〜8分前（全レース）",
            "update_timing_text": "custom",
        }
        snap = build_cleared_snapshot("2026-08-01", prev=prev)
        self.assertEqual(snap["pre_race_trigger_mode"], "6_8")
        self.assertEqual(snap["update_timing_text"], "custom")


if __name__ == "__main__":
    unittest.main()

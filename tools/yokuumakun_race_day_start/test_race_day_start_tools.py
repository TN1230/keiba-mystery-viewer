#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from pathlib import Path


class StartPackLayoutTest(unittest.TestCase):
    def test_files_exist(self):
        here = Path(__file__).resolve().parent
        for name in (
            "race_day_start_wrapper.sh",
            "race_day_start_miss_watch.py",
            "ensure_race_day_start_cron.sh",
            "install_race_day_start_timer.py",
            "bootstrap_on_server.sh",
            "yokuum-race-day-start.timer.example",
            "yokuum-race-day-start-guard.timer.example",
        ):
            self.assertTrue((here / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()

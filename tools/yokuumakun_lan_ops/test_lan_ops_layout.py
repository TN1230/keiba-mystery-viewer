#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from pathlib import Path


class LanOpsLayoutTest(unittest.TestCase):
    def test_files_exist(self):
        here = Path(__file__).resolve().parent
        for name in (
            "README.md",
            "deploy_from_windows.ps1",
            "status_from_windows.ps1",
            "deploy_paramiko.py",
            "status_paramiko.py",
        ):
            self.assertTrue((here / name).is_file(), name)

    def test_timetable_deploy_exists(self):
        target = (
            Path(__file__).resolve().parent.parent
            / "yokuumakun_race_day_timetable"
            / "deploy_paramiko.py"
        )
        self.assertTrue(target.is_file())


if __name__ == "__main__":
    unittest.main()

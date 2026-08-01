#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from pathlib import Path


class TimetableDeployLayoutTest(unittest.TestCase):
    def test_deploy_files_exist(self):
        here = Path(__file__).resolve().parent
        for name in (
            "deploy_paramiko.py",
            "deploy_from_windows.ps1",
            "apply_uploaded_packs.sh",
            "bootstrap_on_server.sh",
            "README.md",
        ):
            self.assertTrue((here / name).is_file(), name)

    def test_upload_map_sources_exist(self):
        import deploy_paramiko as dep

        missing = [str(src) for src, _ in dep.UPLOAD_MAP if not src.is_file()]
        self.assertEqual(missing, [])

    def test_apply_script_has_no_github_curl(self):
        text = (Path(__file__).resolve().parent / "apply_uploaded_packs.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("raw.githubusercontent.com", text)
        self.assertIn("install_race_day_start_timer.py", text)


if __name__ == "__main__":
    unittest.main()

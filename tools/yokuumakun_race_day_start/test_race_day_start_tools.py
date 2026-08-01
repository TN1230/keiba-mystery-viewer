#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_install_skips_same_file_copy(self):
        import install_race_day_start_timer as inst

        here = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "server_deployment"
            dest.mkdir()
            for name in (
                "race_day_start_wrapper.sh",
                "race_day_start_miss_watch.py",
                "yokuum-race-day-start.service.example",
                "yokuum-race-day-start.timer.example",
                "yokuum-race-day-start-guard.service.example",
                "yokuum-race-day-start-guard.timer.example",
                "install_race_day_start_timer.py",
            ):
                (dest / name).write_text((here / name).read_text(encoding="utf-8"), encoding="utf-8")

            # Pretend the installer lives inside server_deployment (same as prod)
            with mock.patch.object(inst, "__file__", str(dest / "install_race_day_start_timer.py")):
                with mock.patch.object(
                    inst,
                    "_sudo_run",
                    return_value=mock.Mock(returncode=0, stdout="", stderr=""),
                ):
                    with mock.patch.object(inst.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="enabled\n", stderr="")):
                        # Patch Path(__file__) usage by running main with root=td after
                        # rewriting install to use mocked __file__ parent — call copy loop logic
                        # via main: it uses Path(__file__).parent which is mocked module __file__
                        rc = inst.main([str(dest / "install_race_day_start_timer.py"), str(root)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()

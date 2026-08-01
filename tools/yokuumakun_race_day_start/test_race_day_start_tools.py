#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
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
                with mock.patch.dict(os.environ, {"YOKUMAKUN_SUDO_PASS": "test-sudo-pass"}):
                    with mock.patch.object(
                        inst,
                        "_sudo_run",
                        return_value=mock.Mock(returncode=0, stdout="", stderr=""),
                    ):
                        with mock.patch.object(
                            inst.subprocess,
                            "run",
                            return_value=mock.Mock(returncode=0, stdout="enabled\n", stderr=""),
                        ):
                            rc = inst.main([str(dest / "install_race_day_start_timer.py"), str(root)])
            self.assertEqual(rc, 0)

    def test_rejects_placeholder_sudo_pass(self):
        import install_race_day_start_timer as inst

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "server_deployment").mkdir()
            env = {
                k: v
                for k, v in os.environ.items()
                if k
                not in ("YOKUMAKUN_SUDO_PASS", "YOKUMAKUN_SSH_PASS", "SUDO_PASSWORD")
            }
            env["YOKUMAKUN_SUDO_PASS"] = "…"
            with mock.patch.dict(os.environ, env, clear=True):
                rc = inst.main(["install_race_day_start_timer.py", str(root)])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()

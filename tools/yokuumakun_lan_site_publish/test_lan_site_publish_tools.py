#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class DayRowsTests(unittest.TestCase):
    def test_day_rows_from_nested_info(self) -> None:
        from force_publish_public_snapshot import _day_rows_from_races, _sample_race_diag

        races = {
            "202601010301": {
                "info": {"place": "札幌", "R": "1", "name": "未勝利", "start_time": "10:00"},
                "prediction": object(),
                "predicted_at": "2026-08-01 10:00:00",
            },
            "202601010302": {
                "info": {"place": "札幌", "R": "2", "name": "未勝利", "start_time": "10:30"},
                "prediction": None,
            },
        }
        rows = _day_rows_from_races(races)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["race_id"], "202601010301")
        self.assertEqual(rows[0]["place"], "札幌")
        diag = _sample_race_diag(races)
        self.assertEqual(diag["n"], 2)
        self.assertTrue(diag["has_prediction"])


class RemoteBootstrapInstallTests(unittest.TestCase):
    def test_install_compiles(self) -> None:
        from install_remote_bootstrap_endpoint import install

        sample = '''#!/usr/bin/env python3
import sys
import json
from typing import Any

class H:
    def _require_session(self):
        return "t", {}
    def _handle_publish_public_snapshot(self) -> None:
        pass
    def do_POST(self):
        path = "/x"
        if path == "/admin/publish-public-snapshot":
            self._handle_publish_public_snapshot()
            return
'''
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "admin_panel_api.py").write_text(sample, encoding="utf-8")
            install(root)
            text = (root / "admin_panel_api.py").read_text(encoding="utf-8")
            compile(text, "admin_panel_api.py", "exec")
            self.assertIn("/admin/remote-bootstrap", text)
            # re-install idempotent
            install(root)
            text2 = (root / "admin_panel_api.py").read_text(encoding="utf-8")
            compile(text2, "admin_panel_api.py", "exec")
            self.assertEqual(text2.count("def _handle_remote_bootstrap"), 1)


if __name__ == "__main__":
    raise SystemExit(unittest.main())

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


class StandaloneBuildTests(unittest.TestCase):
    def test_build_snapshot_from_mock_cache(self) -> None:
        from standalone_publish_from_cache import (
            build_snapshot,
            _format_mark_map,
            _fmt_dev,
        )

        self.assertEqual(_format_mark_map({"◎": 4, "○": 12, "▲": 3, "△": [6, 9], "☆": 11}), "◎4○12▲3△6,9☆11")
        self.assertEqual(_fmt_dev(57.365558433332595), 57.4)
        races = {
            "202601010301": {
                "info": {
                    "place": "札幌",
                    "R": "1",
                    "name": "２歳未勝利",
                    "start_time": "10:00",
                    "weather": "晴",
                    "baba": "良",
                },
                "dev": 57.365558433332595,
                "rank": "C+",
                "holmes_gate_predict_snap": {"holmes_index": 71},
                "hunter_mode": True,
                "hunter_label": "ハンター",
                "hunter_marks": {"◎": 4, "○": 12, "▲": 3, "△": [6, 9], "☆": 11},
                "watson_marks": {"◎": 4, "○": 12},
                "prediction": [
                    {
                        "枠番": 4,
                        "馬番": 4,
                        "馬名": "テスト",
                        "騎手": "騎手A",
                        "単勝": 3.5,
                        "人気": 1,
                        "prob_win": 0.2,
                        "prob_place": 0.4,
                        "馬指数": 100,
                    },
                    {
                        "枠番": 1,
                        "馬番": 12,
                        "馬名": "テスト2",
                        "騎手": "騎手B",
                        "単勝": 5.0,
                        "人気": 2,
                        "prob_win": 0.1,
                        "prob_place": 0.3,
                        "馬指数": 80,
                    },
                ],
                "df": [
                    {
                        "枠番": 4,
                        "馬番": 4,
                        "馬名": "テスト",
                        "騎手": "騎手A",
                        "脚質": "先行",
                        "単勝": 3.5,
                        "人気": 1,
                        "斤量": 55,
                        "性齢": "牡2",
                        "馬体重": 450,
                    },
                    {
                        "枠番": 1,
                        "馬番": 12,
                        "馬名": "テスト2",
                        "騎手": "騎手B",
                        "脚質": "差し",
                        "単勝": 5.0,
                        "人気": 2,
                        "斤量": 55,
                        "性齢": "牝2",
                        "馬体重": 440,
                    },
                ],
                "predicted_at": "2026-08-01 10:40:00",
            }
        }
        snap = build_snapshot(races, "2026-08-01")
        self.assertEqual(snap["race_count"], 1)
        self.assertEqual(snap["venue_count"], 1)
        self.assertEqual(snap["venues"][0]["place"], "札幌")
        race = snap["venues"][0]["races"][0]
        self.assertEqual(race["dev"], 57.4)
        self.assertEqual(race["holmes_index"], "71")
        self.assertEqual(race["cells"]["ハ/ホプ"], "ハンター")
        self.assertTrue(race["shutuba"]["rows"])
        # default order = higher 推定3着内率 first (馬番4)
        self.assertEqual(race["shutuba"]["rows"][0]["馬番"], "4")
        self.assertIn("◎", race["marks"]["ハ/ホプ"])


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

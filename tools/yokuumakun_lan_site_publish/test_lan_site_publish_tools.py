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
    def test_fmt_bataiju_integer(self) -> None:
        from standalone_publish_from_cache import _fmt_bataiju

        self.assertEqual(_fmt_bataiju(528.0), "528")
        self.assertEqual(_fmt_bataiju("486.0"), "486")
        self.assertEqual(_fmt_bataiju(480), "480")
        self.assertEqual(_fmt_bataiju("480(+4)"), "480(+4)")
        self.assertEqual(_fmt_bataiju(""), "")
        self.assertEqual(_fmt_bataiju(None), "")

    def test_fmt_kinryo_half_kg(self) -> None:
        from standalone_publish_from_cache import _fmt_kinryo

        self.assertEqual(_fmt_kinryo(57.0), "57")
        self.assertEqual(_fmt_kinryo("55.0"), "55")
        self.assertEqual(_fmt_kinryo(55.5), "55.5")
        self.assertEqual(_fmt_kinryo("54.5"), "54.5")
        self.assertEqual(_fmt_kinryo(55), "55")
        self.assertEqual(_fmt_kinryo(""), "")
        self.assertEqual(_fmt_kinryo(None), "")

    def test_rejects_gate_threshold_score_25(self) -> None:
        from standalone_publish_from_cache import _extract_holmes_score

        # Edge/gate の score=25 はホームズ指数ではない
        self.assertIsNone(
            _extract_holmes_score(
                {"best_score": 25, "holmes_gate_predict_snap": {"score": 25, "index": 25}},
                "202601010301",
            )
        )
        self.assertEqual(
            _extract_holmes_score(
                {"holmes_gate_predict_snap": {"score": 25, "holmes_index": 71}},
                "202601010301",
            ),
            71.0,
        )

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
                "best_score": 25,  # must not become holmes_index
                "holmes_gate_predict_snap": {"score": 25, "holmes_index": 71},
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
                        "斤量": 55.0,
                        "性齢": "牡2",
                        "馬体重": 450.0,
                    },
                    {
                        "枠番": 1,
                        "馬番": 12,
                        "馬名": "テスト2",
                        "騎手": "騎手B",
                        "脚質": "差し",
                        "単勝": 5.0,
                        "人気": 2,
                        "斤量": 55.0,
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
        self.assertEqual(race["shutuba"]["rows"][0]["馬体重"], "450")
        self.assertEqual(race["shutuba"]["rows"][0]["斤量"], "55")
        self.assertIn("◎", race["marks"]["ハ/ホプ"])


class HolmesOfficialApiTests(unittest.TestCase):
    def test_invoke_build_public_snapshot_uses_races_kwarg(self) -> None:
        """Server dump: build_public_snapshot(*, races, day_rows, schedule_date=None)."""
        from official_republish_from_cache import _invoke_build_public_snapshot
        import types

        seen: dict = {}

        def build_public_snapshot(*, races, day_rows, schedule_date=None):
            seen["races"] = races
            seen["day_rows"] = day_rows
            seen["schedule_date"] = schedule_date
            return {
                "schema_version": 3,
                "race_count": len(day_rows),
                "venues": [],
                "schedule_date": schedule_date,
            }

        mod = types.SimpleNamespace(build_public_snapshot=build_public_snapshot)
        races = {"rid1": {"info": {"place": "札幌", "R": 1}}}
        rows = [types.SimpleNamespace(race_id="rid1", best_score=71)]
        snap = _invoke_build_public_snapshot(mod, day="2026-08-01", day_rows=rows, races=races)
        self.assertEqual(seen["schedule_date"], "2026-08-01")
        self.assertIs(seen["races"], races)
        self.assertEqual(seen["day_rows"], rows)
        self.assertEqual(snap["race_count"], 1)

    def test_invoke_ignores_legacy_kwargs_not_in_signature(self) -> None:
        from official_republish_from_cache import _invoke_build_public_snapshot
        import types

        def build_public_snapshot(*, races, day_rows, schedule_date=None):
            return {"ok": True, "n": len(races)}

        mod = types.SimpleNamespace(build_public_snapshot=build_public_snapshot)
        # Must not TypeError on internal candidates like races_by_id/venues_override
        snap = _invoke_build_public_snapshot(
            mod, day="2026-08-01", day_rows=[], races={"a": {}}
        )
        self.assertTrue(snap["ok"])

    def test_blank_holmes_ranks_are_pending(self) -> None:
        from standalone_publish_from_cache import _apply_holmes_ranks

        races = [{"holmes_index": ""}, {"holmes_index": ""}]
        _apply_holmes_ranks(races)
        self.assertEqual(races[0]["holmes_rank_text"], "算出前")
        self.assertIsNone(races[0]["holmes_index_rank"])

    def test_prev_week_ref_range_excludes_bad_constants(self) -> None:
        from standalone_publish_from_cache import _as_holmes_score, _holmes_valid_range
        import standalone_publish_from_cache as sp

        sp._holmes_range_cache = None
        lo, hi = _holmes_valid_range()
        self.assertLessEqual(lo, 41.0)
        self.assertGreaterEqual(hi, 90.0)
        self.assertIsNone(_as_holmes_score(25))
        self.assertIsNone(_as_holmes_score(5))
        self.assertEqual(_as_holmes_score(71), 71.0)


class KwargsFilterTests(unittest.TestCase):
    def test_filter_drops_unknown_kwargs(self) -> None:
        from official_republish_from_cache import (
            _filter_kwargs_for_callable,
            _make_kwargs_filter_wrapper,
            _patch_build_race_edge_row_kwargs,
        )
        import sys
        import types

        def build_race_edge_row(*, marks_hunter=None, race_id=None):
            return {"marks_hunter": marks_hunter, "race_id": race_id}

        filtered = _filter_kwargs_for_callable(
            build_race_edge_row,
            {"marks_hunter": {"◎": 1}, "marks_baker": {"◎": 2}, "race_id": "x"},
        )
        self.assertEqual(set(filtered), {"marks_hunter", "race_id"})
        self.assertNotIn("marks_baker", filtered)

        wrapped = _make_kwargs_filter_wrapper(build_race_edge_row)
        out = wrapped(marks_hunter={"◎": 3}, marks_baker={"◎": 9}, race_id="rid1")
        self.assertEqual(out["marks_hunter"], {"◎": 3})
        self.assertEqual(out["race_id"], "rid1")

        mod = types.ModuleType("fake_edge_mod_for_kwargs_test")
        mod.build_race_edge_row = build_race_edge_row  # type: ignore[attr-defined]
        sys.modules[mod.__name__] = mod
        try:
            n = _patch_build_race_edge_row_kwargs()
            self.assertGreaterEqual(n, 1)
            fn = mod.build_race_edge_row
            self.assertTrue(getattr(fn, "_kwargs_filtered", False))
            # unknown marks_baker must not raise
            row = fn(marks_hunter={"◎": 4}, marks_baker={"◎": 8}, race_id="rid2")
            self.assertEqual(row["race_id"], "rid2")
            # second patch is idempotent
            n2 = _patch_build_race_edge_row_kwargs()
            self.assertEqual(n2, 0)
        finally:
            sys.modules.pop(mod.__name__, None)

    def test_patch_rewrites_helper_globals_binding(self) -> None:
        """Collectors that did `from X import build_race_edge_row` keep a bare name in __globals__."""
        from official_republish_from_cache import _patch_build_race_edge_row_kwargs
        import sys
        import types

        # Build a fake edge module via exec so helper lookups use module globals
        # (same as real `from edge import build_race_edge_row` inside a collector).
        src = '''
def build_race_edge_row(*, marks_hunter=None):
    return {"ok": True, "hunter": marks_hunter}

def _collect_day_edge_rows_from_races(races, **_kw):
    out = []
    for r in races:
        row = build_race_edge_row(marks_hunter=r.get("hunter"), marks_baker="BAD")
        out.append(row)
    return out
'''
        edge = types.ModuleType("edge_mod_globals_for_kwargs_test")
        g = edge.__dict__
        exec(src, g)
        sys.modules[edge.__name__] = edge
        try:
            with self.assertRaises(TypeError):
                edge._collect_day_edge_rows_from_races([{"hunter": "◎1"}])

            n = _patch_build_race_edge_row_kwargs()
            self.assertGreaterEqual(n, 1)
            rows = edge._collect_day_edge_rows_from_races([{"hunter": "◎1"}])
            self.assertEqual(rows, [{"ok": True, "hunter": "◎1"}])
            self.assertTrue(
                getattr(
                    edge._collect_day_edge_rows_from_races.__globals__["build_race_edge_row"],
                    "_kwargs_filtered",
                    False,
                )
            )
        finally:
            sys.modules.pop(edge.__name__, None)

    def test_try_direct_build_filters_marks_baker(self) -> None:
        from official_republish_from_cache import _try_direct_build_race_edge_rows
        import types

        edge = types.ModuleType("edge_mod_direct_for_kwargs_test")

        def build_race_edge_row(*, marks_hunter=None, race_info=None, df=None):
            return {
                "ok": True,
                "hunter": marks_hunter,
                "r": (race_info or {}).get("R"),
            }

        edge.build_race_edge_row = build_race_edge_row  # type: ignore[attr-defined]
        races = {
            "rid1": {
                "info": {"place": "札幌", "R": 1, "name": "テスト"},
                "df": object(),
                "hunter_marks": "◎1",
                "baker_marks": "◎2",
                "moriarty_marks": "◎3",
            }
        }
        rows, err = _try_direct_build_race_edge_rows(edge, races)
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hunter"], "◎1")
        self.assertEqual(rows[0]["r"], 1)


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

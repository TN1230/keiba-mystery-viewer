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
        self.assertEqual(race["best_logic"], "hunter")
        self.assertEqual(snap["venues"][0]["matrix"][0]["sui"], "ハンター")


class HolmesSuiTests(unittest.TestCase):
    def test_sui_short_label(self) -> None:
        from standalone_publish_from_cache import _sui_short_label, _normalize_best_logic

        self.assertEqual(_sui_short_label("hunter", "ハンター（夏競馬特化）"), "ハンター")
        self.assertEqual(_sui_short_label("hunter", "ホプキンス（新馬戦特化）"), "ホプキンス")
        self.assertEqual(_sui_short_label("watson", "ワトソン"), "ワトソン")
        key, lab = _normalize_best_logic("ホプキンス（新馬戦特化）")
        self.assertEqual(key, "hunter")
        self.assertIn("ホプキンス", lab)
        self.assertEqual(_sui_short_label(key, lab), "ホプキンス")

    def test_pick_best_logic_prefers_edge_not_mark_order(self) -> None:
        from standalone_publish_from_cache import _pick_best_logic

        marks = {
            "watson": {"◎": 1},
            "irene": {"◎": 2},
            "hunter": None,
            "moriarty": None,
        }
        # 印だけ見ると irene になりがちだったが、Edge 推が watson なら watson
        key, lab = _pick_best_logic(marks, {}, edge_best=("watson", "ワトソン"))
        self.assertEqual(key, "watson")
        self.assertEqual(lab, "ワトソン")
        # Edge 無し・明示無しなら推測しない
        key2, lab2 = _pick_best_logic(marks, {})
        self.assertEqual(lab2, "-")


class MatrixCellsTests(unittest.TestCase):
    def test_cells_for_does_not_hardcode_placeholders(self) -> None:
        from standalone_publish_from_cache import _cells_for

        cells = _cells_for(
            "hunter",
            {
                "watson": {"◎": 1, "○": 2},
                "irene": {"◎": 3},
                "hunter": {"◎": 1},
            },
            {"hunter_mode": True, "hunter_label": "ハンター"},
        )
        # 固定の様子・中位帯 / 様子・様子見を全レースに付けない
        self.assertNotEqual(cells["ワ"], "様子・中位帯")
        self.assertNotEqual(cells["アイ"], "様子・様子見")
        self.assertEqual(cells["ハ/ホプ"], "ハンター")

    def test_cells_from_edge_row_uses_display(self) -> None:
        from standalone_publish_from_cache import _cells_from_edge_row
        import types

        class Cell:
            def __init__(self, label: str):
                self._label = label

            def display(self):
                return self._label

        row = types.SimpleNamespace(
            cells={
                "watson": Cell("買・上位帯"),
                "irene": Cell("見送・EV不足"),
                "hunter": Cell("x"),
            }
        )
        cells = _cells_from_edge_row(row)
        self.assertEqual(cells["ワ"], "買・上位帯")
        self.assertEqual(cells["アイ"], "見送・EV不足")

    def test_upload_latest_uses_upload_json_object(self) -> None:
        from official_republish_from_cache import _upload_latest_snapshot
        import types

        calls = {}

        def upload_json_object(path, snap):
            calls["path"] = path
            calls["snap"] = snap
            return ("https://example/latest.json", None)

        mod = types.SimpleNamespace(upload_json_object=upload_json_object)
        res = _upload_latest_snapshot(mod, {"race_count": 1})
        self.assertTrue(res["ok"])
        self.assertEqual(calls["path"], "snapshots/latest.json")

    def test_quality_rejects_identical_placeholder_cells(self) -> None:
        from official_republish_from_cache import _quality

        races = []
        for i in range(12):
            races.append(
                {
                    "dev": 40.0 + i * 0.1,
                    "holmes_index": str(50 + i),
                    "marks": {"ワ": f"◎{i}", "アイ": f"◎{i}", "ハ/ホプ": f"◎{i}"},
                    "cells": {"ワ": "様子・中位帯", "アイ": "様子・様子見", "ハ/ホプ": "ハンター"},
                    "shutuba": {
                        "rows": [
                            {"馬番": "3", "推定3着内率": "40%"},
                            {"馬番": "1", "推定3着内率": "30%"},
                            {"馬番": "5", "推定3着内率": "20%"},
                            {"馬番": "2", "推定3着内率": "10%"},
                        ]
                    },
                }
            )
        snap = {"venues": [{"place": "札幌", "races": races}]}
        q = _quality(snap)
        self.assertFalse(q["ok"])
        self.assertTrue(q["identical_watson_cells"] or q["placeholder_cells"])


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


class PreRacePublishPatchTests(unittest.TestCase):
    def test_injects_after_update_races_cache_entry(self) -> None:
        from patch_pre_race_publish_on_success import patch

        sample = '''#!/usr/bin/env python3
def _dbg_morning_bulk_log(*_a, **_k):
    pass

def main():
    rid = "202604020310"
    rblob = {"predicted_at": "2026-08-01 14:35:00"}
    update_races_cache_entry(rid, rblob)

    title_line = "x"
    line_on = True
'''
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pre_race_auto_predict_worker.py").write_text(sample, encoding="utf-8")
            (root / "force_publish_public_snapshot.py").write_text(
                "def run_publish(*, force=True):\n    return {'ok': True}\n",
                encoding="utf-8",
            )
            patch(root)
            text = (root / "pre_race_auto_predict_worker.py").read_text(encoding="utf-8")
            compile(text, "pre_race_auto_predict_worker.py", "exec")
            self.assertIn("BEGIN pre_race_publish_on_success", text)
            self.assertLess(
                text.index("update_races_cache_entry(rid, rblob)"),
                text.index("BEGIN pre_race_publish_on_success"),
            )
            self.assertLess(
                text.index("END pre_race_publish_on_success"),
                text.index('title_line = "x"'),
            )
            # idempotent
            patch(root)
            text2 = (root / "pre_race_auto_predict_worker.py").read_text(encoding="utf-8")
            self.assertEqual(text2.count("BEGIN pre_race_publish_on_success"), 1)


class PublishWatchDecisionTests(unittest.TestCase):
    def test_parse_dt_accepts_unix_float(self) -> None:
        from morning_bulk_publish_watch import _parse_dt
        from datetime import datetime
        from zoneinfo import ZoneInfo

        jst = ZoneInfo("Asia/Tokyo")
        ts = datetime(2026, 8, 1, 16, 4, 40, tzinfo=jst).timestamp()
        dt = _parse_dt(ts)
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-01 16:04:40")
        dt2 = _parse_dt(str(ts))
        self.assertIsNotNone(dt2)

    def test_classify_anomaly_for_publish_lag(self) -> None:
        from morning_bulk_publish_watch import classify_anomaly

        a = classify_anomaly(
            {
                "action": "force_publish",
                "reason": "cache_newer_than_public",
                "detail": "cache_pred=...",
                "day": "2026-08-01",
            }
        )
        self.assertIsNotNone(a)
        assert a is not None
        self.assertTrue(a["anomaly"])
        self.assertEqual(a["kind"], "viewer_publish_lag_after_predict")
        self.assertIn("異常", a["title"])
        self.assertIsNone(
            classify_anomaly({"action": "noop", "reason": "already_fresh"})
        )

    def test_anomaly_notify_cooldown(self) -> None:
        from morning_bulk_publish_watch import (
            _should_notify_anomaly,
            _load_anomaly_state,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir()
            self.assertTrue(_should_notify_anomaly(root, "viewer_publish_lag_after_predict"))
            # 直後は cooldown
            self.assertFalse(_should_notify_anomaly(root, "viewer_publish_lag_after_predict"))
            st = _load_anomaly_state(root)
            self.assertIn("last_notify_viewer_publish_lag_after_predict", st)

    def test_cache_newer_than_public_triggers_publish(self) -> None:
        from morning_bulk_publish_watch import decide_publish
        import pickle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            (logs / "morning_bulk_done_2026-08-01.flag").write_text("ok", encoding="utf-8")
            races = {
                "202604020309": {"predicted_at": "2026-08-01 14:05:54"},
                "202604020310": {"predicted_at": "2026-08-01 14:35:10"},
            }
            with (logs / "morning_bulk_races_20260801.pkl").open("wb") as f:
                pickle.dump(races, f)
            snap = {
                "schedule_date": "2026-08-01",
                "race_count": 2,
                "updated_at": "2026-08-01T14:33:35",
                "venues": [
                    {
                        "place": "札幌",
                        "races": [
                            {
                                "R": "9",
                                "start_time": "14:20",
                                "predicted_at": "2026-08-01 14:05:54",
                            },
                            {
                                "R": "10",
                                "start_time": "14:50",
                                "predicted_at": "2026-08-01 10:34:56",
                            },
                        ],
                    }
                ],
            }
            out = decide_publish(root, "2026-08-01", snap)
            self.assertEqual(out["action"], "force_publish")
            self.assertEqual(out["reason"], "cache_newer_than_public")

    def test_already_fresh_is_noop(self) -> None:
        from morning_bulk_publish_watch import decide_publish
        import pickle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            (logs / "morning_bulk_done_2026-08-01.flag").write_text("ok", encoding="utf-8")
            races = {"rid": {"predicted_at": "2026-08-01 14:05:54"}}
            with (logs / "morning_bulk_races_20260801.pkl").open("wb") as f:
                pickle.dump(races, f)
            snap = {
                "schedule_date": "2026-08-01",
                "race_count": 1,
                "updated_at": datetime_now_iso_fresh(),
                "venues": [
                    {
                        "place": "札幌",
                        "races": [
                            {
                                "R": "9",
                                "start_time": "23:50",
                                "predicted_at": "2026-08-01 14:05:54",
                            }
                        ],
                    }
                ],
            }
            out = decide_publish(root, "2026-08-01", snap)
            self.assertEqual(out["action"], "noop")
            self.assertEqual(out["reason"], "already_fresh")

    def test_recent_updated_at_does_not_hide_stale_prerace(self) -> None:
        """他レースの直近 publish があっても、キャッシュが直前更新済みなら再 publish。"""
        from morning_bulk_publish_watch import decide_publish
        import pickle
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        jst = ZoneInfo("Asia/Tokyo")
        now = datetime.now(jst)
        # 12分後に発走するレース（直前窓内）
        start_dt = now + timedelta(minutes=12)
        start = start_dt.strftime("%H:%M")
        # キャッシュだけ発走15分前に更新済み（公開は朝のまま）
        cache_pred = (start_dt - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            (logs / "morning_bulk_done_2026-08-01.flag").write_text("ok", encoding="utf-8")
            # max を揃えるため別レースも同じ時刻にして cache_newer(max) を回避
            races = {
                "202604020311": {"predicted_at": cache_pred},
                "202604020307": {"predicted_at": cache_pred},
            }
            with (logs / "morning_bulk_races_20260801.pkl").open("wb") as f:
                pickle.dump(races, f)
            snap = {
                "schedule_date": "2026-08-01",
                "race_count": 2,
                "updated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),  # 直前に更新済み
                "venues": [
                    {
                        "place": "新潟",
                        "races": [
                            {
                                "race_id": "202604020311",
                                "place": "新潟",
                                "R": "11",
                                "start_time": "18:00",
                                "predicted_at": cache_pred,
                            },
                            {
                                "race_id": "202604020307",
                                "place": "新潟",
                                "R": "7",
                                "start_time": start,
                                "predicted_at": "2026-08-01 10:36:33",
                            },
                        ],
                    }
                ],
            }
            out = decide_publish(root, "2026-08-01", snap)
            self.assertEqual(out["action"], "force_publish")
            # max 比較または per-race / prerace のいずれかで拾う
            self.assertIn(
                out["reason"],
                ("cache_newer_than_public", "stale_during_prerace"),
            )

    def test_float_cache_predicted_at_triggers_publish(self) -> None:
        """本番キャッシュは predicted_at が Unix float。これを読めないと恒久自動更新が死ぬ。"""
        from morning_bulk_publish_watch import decide_publish
        import pickle
        from datetime import datetime
        from zoneinfo import ZoneInfo

        jst = ZoneInfo("Asia/Tokyo")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            (logs / "morning_bulk_done_2026-08-01.flag").write_text("ok", encoding="utf-8")
            races = {
                "202601010312": {
                    "predicted_at": datetime(2026, 8, 1, 15, 46, 44, tzinfo=jst).timestamp()
                },
                "202604020308": {
                    "predicted_at": datetime(2026, 8, 1, 16, 4, 40, tzinfo=jst).timestamp()
                },
            }
            with (logs / "morning_bulk_races_20260801.pkl").open("wb") as f:
                pickle.dump(races, f)
            snap = {
                "schedule_date": "2026-08-01",
                "race_count": 2,
                "updated_at": "2026-08-01T15:57:19",
                "venues": [
                    {
                        "place": "札幌",
                        "races": [
                            {
                                "race_id": "202601010312",
                                "R": "12",
                                "start_time": "16:01",
                                "predicted_at": "2026-08-01 10:36:51",
                            }
                        ],
                    },
                    {
                        "place": "新潟",
                        "races": [
                            {
                                "race_id": "202604020308",
                                "R": "8",
                                "start_time": "16:20",
                                "predicted_at": "2026-08-01 10:37:27",
                            }
                        ],
                    },
                ],
            }
            out = decide_publish(root, "2026-08-01", snap)
            self.assertEqual(out["action"], "force_publish")
            self.assertEqual(out["reason"], "cache_newer_than_public")

    def test_per_race_cache_newer_triggers_publish(self) -> None:
        from morning_bulk_publish_watch import decide_publish
        import pickle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            logs.mkdir()
            (logs / "morning_bulk_done_2026-08-01.flag").write_text("ok", encoding="utf-8")
            # max は公開と同じ 15:09 だが、7R だけキャッシュが新しい
            races = {
                "202604020311": {"predicted_at": "2026-08-01 15:09:37"},
                "202604020307": {"predicted_at": "2026-08-01 15:09:37"},
            }
            with (logs / "morning_bulk_races_20260801.pkl").open("wb") as f:
                pickle.dump(races, f)
            snap = {
                "schedule_date": "2026-08-01",
                "race_count": 2,
                "updated_at": "2026-08-01T15:11:16",
                "venues": [
                    {
                        "place": "新潟",
                        "races": [
                            {
                                "race_id": "202604020311",
                                "R": "11",
                                "start_time": "18:00",
                                "predicted_at": "2026-08-01 15:09:37",
                            },
                            {
                                "race_id": "202604020307",
                                "R": "7",
                                "start_time": "15:45",
                                "predicted_at": "2026-08-01 10:36:33",
                            },
                        ],
                    }
                ],
            }
            out = decide_publish(root, "2026-08-01", snap)
            self.assertEqual(out["action"], "force_publish")
            self.assertEqual(out["reason"], "cache_newer_than_public")
            self.assertIn("per_race_cache_newer", out.get("detail") or "")


def datetime_now_iso_fresh() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%dT%H:%M:%S")


class PaceLabelTests(unittest.TestCase):
    def test_normalize_known_labels(self) -> None:
        from race_pace_label import normalize_pace_label

        self.assertEqual(normalize_pace_label("やや遅"), "やや遅")
        self.assertEqual(normalize_pace_label("ペース:中"), "中")
        self.assertEqual(normalize_pace_label("予想ペース:やや速"), "やや速")

    def test_extract_from_stored_field(self) -> None:
        from race_pace_label import extract_pace_fields

        fields = extract_pace_fields({}, {"pace_label": "やや遅"})
        self.assertEqual(fields["pace_label"], "やや遅")
        self.assertEqual(fields["pace_display"], "予想ペース: やや遅")

    def test_enrich_snapshot_pace(self) -> None:
        from race_pace_label import enrich_snapshot_with_pace_label

        snap = {
            "venues": [
                {"races": [{"race_id": "202601010304", "place": "札幌", "R": "4"}]}
            ]
        }
        cache = {"202601010304": {"pace_label": "やや遅", "info": {}}}
        n = enrich_snapshot_with_pace_label(snap, cache)
        self.assertEqual(n, 1)
        self.assertEqual(snap["venues"][0]["races"][0]["pace_label"], "やや遅")


class CourseDistanceTests(unittest.TestCase):
    def test_format_dirt_with_division(self) -> None:
        from race_course_distance import extract_course_distance_fields

        fields = extract_course_distance_fields(
            {"course": "ダ", "distance": 1000, "course_division": "右"}
        )
        self.assertEqual(fields["course"], "ダート")
        self.assertEqual(fields["distance"], "1000")
        self.assertEqual(fields["course_label"], "ダート1000m（右）")

    def test_format_turf(self) -> None:
        from race_course_distance import format_course_label

        self.assertEqual(
            format_course_label(course="芝", distance="1600", course_division=""),
            "芝1600m",
        )

    def test_unknown_division_omitted(self) -> None:
        from race_course_distance import format_course_label, normalize_course_division

        self.assertEqual(normalize_course_division("不明"), "")
        self.assertEqual(
            format_course_label(course="芝", distance="1600", course_division="不明"),
            "芝1600m",
        )

    def test_enrich_snapshot(self) -> None:
        from race_course_distance import enrich_snapshot_with_course_distance

        snap = {
            "venues": [
                {
                    "races": [
                        {"race_id": "202601010301", "place": "札幌", "R": "1"},
                    ]
                }
            ]
        }
        cache = {
            "202601010301": {
                "info": {
                    "course": "ダート",
                    "distance": 1000,
                    "course_division": "右",
                }
            }
        }
        n = enrich_snapshot_with_course_distance(snap, cache)
        self.assertEqual(n, 1)
        r = snap["venues"][0]["races"][0]
        self.assertEqual(r["course_label"], "ダート1000m（右）")


class ImmediateWakeTests(unittest.TestCase):
    def test_pending_forces_publish_decision(self) -> None:
        from morning_bulk_publish_watch import decide_publish
        from viewer_publish_wake import write_pending

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir()
            write_pending(
                reason="pre_race_publish_failed",
                race_id="202608010301",
                error="boom",
                root=root,
            )
            out = decide_publish(root, "2026-08-01", None)
            self.assertEqual(out["action"], "force_publish")
            self.assertEqual(out["reason"], "pending_wake")

    def test_urgent_purchase_title_near_post(self) -> None:
        from morning_bulk_publish_watch import classify_anomaly
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        jst = ZoneInfo("Asia/Tokyo")
        now = datetime.now(jst)
        start = now + timedelta(minutes=15)
        hhmm = start.strftime("%H:%M")
        snap = {
            "venues": [
                {
                    "races": [
                        {
                            "race_id": "202608010301",
                            "place": "札幌",
                            "R": "1",
                            "start_time": hhmm,
                            "predicted_at": "2026-08-01 10:00:00",
                        }
                    ]
                }
            ]
        }
        a = classify_anomaly(
            {
                "action": "force_publish",
                "reason": "cache_newer_than_public",
                "detail": "x",
                "day": "2026-08-01",
            },
            snap,
        )
        self.assertIsNotNone(a)
        assert a is not None
        self.assertTrue(a.get("urgent_purchase_window"))
        self.assertIn("発走間近", a["title"])

    def test_inject_block_mentions_wake(self) -> None:
        from patch_pre_race_publish_on_success import _inject_block

        block = _inject_block("    ")
        self.assertIn("mark_pending_and_wake", block)
        self.assertIn("viewer_publish_wake", block)
        self.assertIn("public_viewer_publish_returned_not_ok", block)


if __name__ == "__main__":
    raise SystemExit(unittest.main())

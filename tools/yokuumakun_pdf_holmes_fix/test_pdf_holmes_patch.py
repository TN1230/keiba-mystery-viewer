#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


SAMPLE = '''#!/usr/bin/env python3
def _holmes_index_score_and_rank_texts(rid, race_info):
    return "-", "算出前"

def _load_day_holmes_score_snap():
    return {}

def _apply_day_holmes_rank_overrides_to_race_info(info):
    return None

def _export_marked_syutsuba_pdf_with_meta(
    rid: str,
    *,
    race_info_override: dict | None = None,
    pdf_race_title_tag: str | None = None,
    persist_session_help_url: bool = True,
    pdf_help_warnings: bool = True,
    line_notify_holmes_gate: bool = False,
) -> tuple[str | None, str]:
    race_info = race_info_override or {}
    if not race_info:
        return None, ""

    holmes_score_text = "-"
    holmes_rank_text = "算出前"
    meta = (
        f"天気:曇 馬場:重 / 期待値偏差:35.0 / 期待値ランク:C / "
        f"ホームズ指数:{holmes_score_text} / 当日レース内順位:{holmes_rank_text} / ペース:中"
    )
    return meta, ""


def other():
    pass
'''


class PatchTests(unittest.TestCase):
    def test_patch_injects_and_rewrites(self) -> None:
        from patch_pdf_holmes_index import patch

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "hwm.py").write_text(SAMPLE, encoding="utf-8")
            patch(root)
            text = (root / "hwm.py").read_text(encoding="utf-8")
            compile(text, "hwm.py", "exec")
            self.assertIn("BEGIN pdf_holmes_resolve_helper", text)
            self.assertIn("BEGIN pdf_holmes_resolve_inject", text)
            self.assertIn("_pdf_holmes_score_txt", text)
            self.assertIn("ホームズ指数:{_pdf_holmes_score_txt}", text)
            # idempotent
            patch(root)
            text2 = (root / "hwm.py").read_text(encoding="utf-8")
            self.assertEqual(text2.count("BEGIN pdf_holmes_resolve_helper"), 1)
            self.assertEqual(text2.count("BEGIN pdf_holmes_resolve_inject"), 1)


if __name__ == "__main__":
    raise SystemExit(unittest.main())

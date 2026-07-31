#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from morning_bulk_test_webhook_filter import (  # noqa: E402
    allow_morning_bulk_test_always,
    apply_to_ops_module,
    is_morning_bulk_ops_event,
    wrap_notify_action,
)
from install_into_ops_discord_notify import (  # noqa: E402
    BEGIN,
    END,
    _insert_inject,
    install,
)


class AllowlistTests(unittest.TestCase):
    def test_non_morning_bulk_always_allowed(self):
        self.assertTrue(allow_morning_bulk_test_always("pre_race_spawn", "ok"))
        self.assertTrue(allow_morning_bulk_test_always("service_stop", "ok"))

    def test_start_end_error_allowed(self):
        for ev in (
            "morning_bulk_worker_start",
            "morning_bulk_worker_done",
            "morning_bulk_worker_fatal",
            "morning_bulk_spawn",
            "admin_morning_bulk_rerun",
            "morning_bulk_odds_suspicion_modem_reboot",
            "morning_bulk_quality_06:00",
        ):
            self.assertTrue(allow_morning_bulk_test_always(ev, "ok"), ev)

    def test_mid_run_suppressed(self):
        for ev in (
            "morning_bulk_cache_flush",
            "morning_bulk_spawn_deferred",
            "morning_bulk_seq_exception_20260801",
            "morning_bulk_progress",
        ):
            self.assertFalse(allow_morning_bulk_test_always(ev, "ok"), ev)

    def test_error_status_allowed_even_if_unknown_event(self):
        self.assertTrue(
            allow_morning_bulk_test_always("morning_bulk_something_weird", "error")
        )

    def test_is_morning_bulk_ops_event(self):
        self.assertTrue(is_morning_bulk_ops_event("morning_bulk_worker_start"))
        self.assertTrue(is_morning_bulk_ops_event("admin_morning_bulk_rerun"))
        self.assertFalse(is_morning_bulk_ops_event("pre_race_spawn"))


class WrapTests(unittest.TestCase):
    def test_wrap_clears_test_always_for_mid_run(self):
        calls = []

        def orig(event, status="ok", detail="", **kwargs):
            calls.append(
                {
                    "event": event,
                    "status": status,
                    "env": os.environ.get("DISCORD_WEBHOOK_TEST_ALWAYS"),
                }
            )
            return True

        wrapped = wrap_notify_action(orig, mod=None)
        with mock.patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_TEST_ALWAYS": "https://example.test/hook"},
            clear=False,
        ):
            wrapped("morning_bulk_cache_flush", status="ok", detail="n=8")
            # 抑制後に env が戻っていること
            self.assertEqual(
                os.environ.get("DISCORD_WEBHOOK_TEST_ALWAYS"),
                "https://example.test/hook",
            )
            wrapped("morning_bulk_worker_start", status="ok", detail="slot=06:00")
            wrapped("pre_race_spawn", status="ok", detail="x")

        self.assertEqual(calls[0]["env"], None)
        self.assertEqual(calls[1]["env"], "https://example.test/hook")
        self.assertEqual(calls[2]["env"], "https://example.test/hook")

    def test_apply_idempotent(self):
        class M:
            @staticmethod
            def notify_action(event, status="ok", detail="", **kwargs):
                return event

        m = M()
        self.assertTrue(apply_to_ops_module(m))
        self.assertFalse(apply_to_ops_module(m))

    def test_wrap_clears_module_cached_url(self):
        class Mod:
            DISCORD_WEBHOOK_TEST_ALWAYS = "https://example.test/hook"
            seen = None

            @staticmethod
            def _orig(event, status="ok", detail="", **kwargs):
                Mod.seen = Mod.DISCORD_WEBHOOK_TEST_ALWAYS
                return True

        Mod.notify_action = staticmethod(Mod._orig)  # placeholder
        wrapped = wrap_notify_action(Mod._orig, mod=Mod)
        with mock.patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_TEST_ALWAYS": "https://example.test/hook"},
            clear=False,
        ):
            wrapped("morning_bulk_cache_flush", status="ok")
            self.assertEqual(Mod.seen, "")
            self.assertEqual(
                Mod.DISCORD_WEBHOOK_TEST_ALWAYS, "https://example.test/hook"
            )


class InstallerTests(unittest.TestCase):
    def test_insert_inject_after_notify_action(self):
        src = (
            "#!/usr/bin/env python3\n"
            "from __future__ import annotations\n"
            "import os\n\n"
            "def notify_action(event, status='ok', detail=''):\n"
            "    return True\n\n"
            "def format_ops_message(event, status='ok', detail=''):\n"
            "    return event\n"
        )
        out = _insert_inject(src)
        self.assertIn(BEGIN, out)
        self.assertIn(END, out)
        self.assertIn("import sys", out)
        # inject は notify_action の後、format_ops_message の前
        i_notify = out.index("def notify_action")
        i_begin = out.index(BEGIN)
        i_fmt = out.index("def format_ops_message")
        self.assertLess(i_notify, i_begin)
        self.assertLess(i_begin, i_fmt)
        # 再適用してもブロックは1つ
        out2 = _insert_inject(out)
        self.assertEqual(out2.count(BEGIN), 1)

    def test_install_copies_and_patches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ops_discord_notify.py").write_text(
                "import os\n\n"
                "def notify_action(event, status='ok', detail=''):\n"
                "    return True\n",
                encoding="utf-8",
            )
            install(root)
            self.assertTrue((root / "morning_bulk_test_webhook_filter.py").is_file())
            text = (root / "ops_discord_notify.py").read_text(encoding="utf-8")
            self.assertIn(BEGIN, text)
            self.assertTrue(
                (root / "ops_discord_notify.py.bak_mb_tw_filter").is_file()
            )


if __name__ == "__main__":
    unittest.main()

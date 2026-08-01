#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import publish_ssh_endpoint as mod  # noqa: E402


class PublishTests(unittest.TestCase):
    def test_main_builds_payload_and_calls_publish(self):
        captured = {}

        def fake_publish(payload):
            captured["payload"] = payload
            return "https://example.test/ssh_endpoint.json"

        buf = StringIO()
        with mock.patch.object(mod, "publish", side_effect=fake_publish):
            with mock.patch("sys.stdout", buf):
                rc = mod.main(
                    ["--host", "bore.pub", "--port", "23456", "--user", "tn"]
                )
        self.assertEqual(rc, 0)
        self.assertEqual(captured["payload"]["host"], "bore.pub")
        self.assertEqual(captured["payload"]["port"], 23456)
        self.assertIn("ssh -p 23456 tn@bore.pub", captured["payload"]["ssh_command"])
        out = buf.getvalue()
        self.assertIn("OK https://example.test/ssh_endpoint.json", out)
        # second line json
        line = [ln for ln in out.splitlines() if ln.startswith("{")][0]
        data = json.loads(line)
        self.assertEqual(data["provider"], "bore")


if __name__ == "__main__":
    unittest.main()

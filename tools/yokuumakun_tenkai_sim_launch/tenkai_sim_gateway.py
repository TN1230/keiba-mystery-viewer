#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GET /tenkai 用ゲートウェイ（一時）。race_progression_sim を別タブ表示向けに起動する。"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

SIM_ENTRY = "race_progression_sim.py"


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    if (here / SIM_ENTRY).is_file() or (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def _py() -> str:
    root = _root()
    v = root / ".venv" / "bin" / "python"
    return str(v) if v.is_file() else sys.executable


def _help_text() -> str:
    root = _root()
    entry = root / SIM_ENTRY
    if not entry.is_file():
        return ""
    try:
        cp = subprocess.run(
            [_py(), str(entry), "--help"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=45,
        )
        return (cp.stdout or "") + (cp.stderr or "")
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _pick_flag(help_txt: str, *cands: str) -> str | None:
    flags = set(re.findall(r"--[a-zA-Z0-9][a-zA-Z0-9\-]*", help_txt or ""))
    for c in cands:
        if c in flags:
            return c
    return None


def run_sim(params: dict[str, str]) -> dict[str, Any]:
    root = _root()
    entry = root / SIM_ENTRY
    if not entry.is_file():
        return {
            "ok": False,
            "error": "missing_sim",
            "message": f"{SIM_ENTRY} が {root} にありません。メイン機 yokuumakun からコピーしてください。",
        }
    help_txt = _help_text()
    race_id = (params.get("race_id") or "").strip()
    place = (params.get("place") or params.get("venue") or "").strip()
    race_no = (params.get("R") or params.get("race_no") or "").strip()
    schedule_date = (params.get("schedule_date") or params.get("kaisai_date") or "").strip()

    cmd = [_py(), str(entry)]
    rid_flag = _pick_flag(help_txt, "--race-id", "--race_id", "--rid")
    place_flag = _pick_flag(help_txt, "--place", "--venue", "--kaisai")
    r_flag = _pick_flag(help_txt, "--R", "--race-no", "--race_no", "--r")
    date_flag = _pick_flag(help_txt, "--schedule-date", "--kaisai-date", "--date")
    json_flag = _pick_flag(help_txt, "--json-out", "--output", "--out")
    html_flag = _pick_flag(help_txt, "--html-out", "--html")

    if rid_flag and race_id:
        cmd += [rid_flag, race_id]
    elif race_id and "--help" not in help_txt:
        # help が取れない場合のフォールバック
        cmd += ["--race-id", race_id]
    if place_flag and place:
        cmd += [place_flag, place]
    if r_flag and race_no:
        cmd += [r_flag, race_no]
    if date_flag and schedule_date:
        cmd += [date_flag, schedule_date]

    tmp_json = None
    tmp_html = None
    if json_flag:
        tmp_json = tempfile.NamedTemporaryFile(prefix="tenkai_", suffix=".json", delete=False)
        tmp_json.close()
        cmd += [json_flag, tmp_json.name]
    if html_flag:
        tmp_html = tempfile.NamedTemporaryFile(prefix="tenkai_", suffix=".html", delete=False)
        tmp_html.close()
        cmd += [html_flag, tmp_html.name]

    try:
        cp = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "YOKUMAKUN_ROOT": str(root)},
        )
    except Exception as e:
        return {"ok": False, "error": "exec_failed", "message": f"{type(e).__name__}: {e}", "cmd": cmd}

    result: dict[str, Any] = {
        "ok": cp.returncode == 0,
        "returncode": cp.returncode,
        "cmd": cmd,
        "stdout": (cp.stdout or "")[-4000:],
        "stderr": (cp.stderr or "")[-2000:],
        "cli_flags_detected": sorted(set(re.findall(r"--[a-zA-Z0-9][a-zA-Z0-9\-]*", help_txt))),
    }
    if tmp_html and Path(tmp_html.name).is_file():
        try:
            result["html"] = Path(tmp_html.name).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result["html_error"] = f"{type(e).__name__}: {e}"
        finally:
            try:
                Path(tmp_html.name).unlink(missing_ok=True)
            except Exception:
                pass
    if tmp_json and Path(tmp_json.name).is_file():
        try:
            raw = Path(tmp_json.name).read_text(encoding="utf-8", errors="replace")
            try:
                result["data"] = json.loads(raw)
            except Exception:
                result["data_raw"] = raw[:8000]
        except Exception as e:
            result["json_error"] = f"{type(e).__name__}: {e}"
        finally:
            try:
                Path(tmp_json.name).unlink(missing_ok=True)
            except Exception:
                pass
    elif (cp.stdout or "").strip().startswith(("{", "[")):
        try:
            result["data"] = json.loads(cp.stdout)
        except Exception:
            pass
    if not result.get("ok") and not result.get("message"):
        result["message"] = (cp.stderr or cp.stdout or "simulation failed")[:500]
    return result


def render_html(params: dict[str, str]) -> tuple[int, bytes, str]:
    race_id = (params.get("race_id") or "").strip()
    title = "展開シミュレーション"
    if not race_id:
        body = (
            f"<h1>{html.escape(title)}</h1>"
            "<p>race_id が必要です。管理画面のレースボタンから開いてください。</p>"
        )
        page = _page(title, body)
        return 400, page.encode("utf-8"), "text/html; charset=utf-8"

    result = run_sim(params)
    if result.get("html"):
        return 200, str(result["html"]).encode("utf-8"), "text/html; charset=utf-8"

    place = html.escape(params.get("place") or params.get("venue") or "")
    rn = html.escape(params.get("R") or params.get("race_no") or "")
    heading = f"{place} {rn}R".strip() or html.escape(race_id)

    if result.get("ok") and result.get("data") is not None:
        pretty = html.escape(json.dumps(result["data"], ensure_ascii=False, indent=2))
        body = (
            f"<h1>{html.escape(title)}</h1>"
            f"<p class='meta'>{heading} / race_id={html.escape(race_id)}</p>"
            f"<pre>{pretty}</pre>"
        )
        return 200, _page(title, body).encode("utf-8"), "text/html; charset=utf-8"

    if result.get("error") == "missing_sim":
        body = (
            f"<h1>{html.escape(title)}</h1>"
            f"<p class='err'>{html.escape(str(result.get('message') or ''))}</p>"
            "<p>Windows LAN から <code>tools/yokuumakun_tenkai_sim_launch/deploy_from_windows.ps1</code> を実行してください。</p>"
        )
        return 503, _page(title, body).encode("utf-8"), "text/html; charset=utf-8"

    # 失敗時もコマンドと出力を見せる（一時運用向け）
    pretty = html.escape(json.dumps(result, ensure_ascii=False, indent=2))
    body = (
        f"<h1>{html.escape(title)}</h1>"
        f"<p class='meta'>{heading} / race_id={html.escape(race_id)}</p>"
        f"<p class='err'>{html.escape(str(result.get('message') or '実行に失敗しました'))}</p>"
        f"<pre>{pretty}</pre>"
    )
    code = 200 if result.get("ok") else 500
    return code, _page(title, body).encode("utf-8"), "text/html; charset=utf-8"


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: "Segoe UI", "Hiragino Sans", sans-serif; margin: 1.25rem; background: #f6f7fb; color: #0f172a; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 .5rem; }}
    .meta {{ color: #475569; margin: 0 0 1rem; }}
    .err {{ color: #b91c1c; }}
    pre {{ background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 10px; overflow: auto; white-space: pre-wrap; }}
    code {{ background: #e2e8f0; padding: .1rem .35rem; border-radius: 4px; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def params_from_query(query: str) -> dict[str, str]:
    qs = parse_qs(query or "", keep_blank_values=False)
    out: dict[str, str] = {}
    for k, vals in qs.items():
        if vals:
            out[k] = vals[0]
    return out

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""キャッシュから印付き出馬表PDFを再生成し Supabase へ上げ、latest.json の pdf_url も更新する。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    if (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
        rt = root / "server_deployment" / "hwm_runtime.env"
        if rt.is_file():
            load_dotenv(rt, override=False)
    except Exception:
        pass


def _load_races(root: Path) -> tuple[str, dict[str, Any]]:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    day = datetime.now(_JST).strftime("%Y-%m-%d")
    try:
        from hwm_server_standalone import (  # type: ignore
            _load_morning_bulk_races_cache,
            effective_schedule_date_iso,
        )

        day = str(effective_schedule_date_iso() or day)
        races = _load_morning_bulk_races_cache(day) or {}
        if races:
            return day, races
    except Exception as e:
        print("helper_cache_err", type(e).__name__, e)

    import pickle

    logs = root / "logs"
    ymd = day.replace("-", "")
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        fp = logs / name
        if not fp.is_file():
            continue
        with fp.open("rb") as f:
            races = pickle.load(f)
        if isinstance(races, dict) and races:
            return day, races
    return day, {}


def main() -> int:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _load_env(root)

    day, races = _load_races(root)
    out: dict[str, Any] = {"day": day, "n_cache": len(races), "ok": 0, "fail": 0, "items": []}
    if not races:
        out["error"] = "empty_cache"
        print(json.dumps(out, ensure_ascii=False))
        return 1

    # day holmes snap を可能な範囲で準備
    try:
        from hwm import _persist_day_holmes_score_snap  # type: ignore

        _persist_day_holmes_score_snap()
    except Exception:
        pass

    from hwm import _export_marked_syutsuba_pdf_with_meta  # type: ignore

    upload = None
    try:
        from hwm import _upload_race_pdf_to_supabase  # type: ignore

        upload = _upload_race_pdf_to_supabase
    except Exception:
        pass

    pdf_by_rid: dict[str, str] = {}
    help_by_rid: dict[str, str] = {}

    for rid, rinfo in sorted(races.items(), key=lambda x: str(x[0])):
        if not isinstance(rinfo, dict):
            continue
        item: dict[str, Any] = {"race_id": str(rid)}
        try:
            path, help_url = _export_marked_syutsuba_pdf_with_meta(
                str(rid),
                race_info_override=rinfo,
                persist_session_help_url=False,
                pdf_help_warnings=False,
                line_notify_holmes_gate=False,
            )
            item["local"] = path
            item["help_url"] = help_url or ""
            if help_url:
                help_by_rid[str(rid)] = str(help_url)
                rinfo["supabase_help_pdf_url"] = str(help_url)
            pub = ""
            if path and upload:
                pub, err = upload(path, str(rid))
                item["upload_err"] = err
                if pub:
                    pub = str(pub)
                    pdf_by_rid[str(rid)] = pub
                    rinfo["supabase_pdf_url"] = pub
                    item["pdf_url"] = pub
            if path:
                out["ok"] += 1
            else:
                out["fail"] += 1
                item["error"] = "export_returned_none"
        except Exception as e:
            out["fail"] += 1
            item["error"] = f"{type(e).__name__}: {e}"
        out["items"].append(item)

    # latest.json の pdf_url を差し替え（公開中スナップがあるとき）
    try:
        import urllib.request

        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        latest_url = (
            "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/"
            "public-viewer/snapshots/latest.json"
        )
        with urllib.request.urlopen(latest_url, timeout=30) as resp:
            snap = json.loads(resp.read().decode())
        n_upd = 0
        for v in snap.get("venues") or []:
            for r in v.get("races") or []:
                rid = str(r.get("race_id") or "")
                if rid in pdf_by_rid:
                    r["pdf_url"] = pdf_by_rid[rid]
                    n_upd += 1
                if rid in help_by_rid:
                    r["help_pdf_url"] = help_by_rid[rid]
        if n_upd:
            snap["updated_at"] = datetime.now(_JST).strftime("%Y-%m-%dT%H:%M:%S")
            url, err = upload_json_object("snapshots/latest.json", snap)
            out["snapshot_pdf_urls_updated"] = n_upd
            out["snapshot_upload"] = {"url": url, "err": err}
    except Exception as e:
        out["snapshot_update_error"] = f"{type(e).__name__}: {e}"

    print(json.dumps(out, ensure_ascii=False, default=str)[:4000])
    # サンプル検証
    try:
        import subprocess
        import tempfile
        import urllib.request

        sample = next((x for x in out["items"] if x.get("pdf_url")), None)
        if sample and sample.get("pdf_url"):
            tmp = Path(tempfile.gettempdir()) / "regen_sample.pdf"
            urllib.request.urlretrieve(sample["pdf_url"], tmp)
            cp = subprocess.run(
                ["pdftotext", "-layout", str(tmp), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            head = "\n".join((cp.stdout or "").splitlines()[:6])
            out_check = {
                "sample_race_id": sample.get("race_id"),
                "header": head,
                "has_numeric_holmes": any(
                    tok.startswith("ホームズ指数:") and not tok.startswith("ホームズ指数:-")
                    for tok in head.replace(" / ", "\n").splitlines()
                    if "ホームズ指数" in tok
                ),
            }
            print(json.dumps(out_check, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"sample_check_error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))

    return 0 if out["ok"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pre_race_auto_predict_worker.py の成功パスで公開 snapshot を publish するようパッチする。

本日(2026-08-01)の成功パターン:
  発走約15分前 → 予想OK → update_races_cache_entry(rid, rblob) → (通知)
公開 latest.json は札幌9R(pred 14:05)まで追いついた後止まり、
札幌10R以降が朝一斉 predicted_at のまま残った。キャッシュ更新直後の
publish が欠落しているため、その直後に強制 publish を差し込む。

publish 失敗時は pending + watch oneshot を即起動し、馬券購入時間を確保する。
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN pre_race_publish_on_success"
END = "# END pre_race_publish_on_success"
WORKER_NAME = "pre_race_auto_predict_worker.py"


def _inject_block(indent: str) -> str:
    lines = [
        BEGIN,
        "try:",
        "    _pub_ok = False",
        "    try:",
        "        from force_publish_public_snapshot import run_publish as _force_pub",
        "        _pub = _force_pub(force=True)",
        "        _pub_ok = bool(isinstance(_pub, dict) and _pub.get('ok'))",
        "        try:",
        '            _dbg_morning_bulk_log(',
        '                "H7",',
        '                "pre_race_auto_predict_worker.py:main",',
        '                "public_viewer_publish",',
        '                {"race_id": rid, "result": str(_pub)[:240], "ok": _pub_ok},',
        "            )",
        "        except Exception:",
        "            pass",
        "    except Exception:",
        "        from hwm import _publish_public_viewer_snapshot",
        "        _publish_public_viewer_snapshot(force=True)",
        "        _pub_ok = True",
        "        try:",
        '            _dbg_morning_bulk_log(',
        '                "H7",',
        '                "pre_race_auto_predict_worker.py:main",',
        '                "public_viewer_publish_hwm",',
        '                {"race_id": rid},',
        "            )",
        "        except Exception:",
        "            pass",
        "    if not _pub_ok:",
        '        raise RuntimeError("public_viewer_publish_returned_not_ok")',
        "except Exception as _pub_e:",
        "    try:",
        '        _dbg_morning_bulk_log(',
        '            "H7",',
        '            "pre_race_auto_predict_worker.py:main",',
        '            "public_viewer_publish_failed",',
        '            {"race_id": rid, "error": f"{type(_pub_e).__name__}: {_pub_e}"},',
        "        )",
        "    except Exception:",
        "        pass",
        "    # 公開遅れ = 購入時間を食う異常。timer 待ちせず直ちに安全網を起こす",
        "    try:",
        "        from viewer_publish_wake import mark_pending_and_wake",
        "        mark_pending_and_wake(",
        '            reason="pre_race_publish_failed",',
        "            race_id=str(rid),",
        '            error=f"{type(_pub_e).__name__}: {_pub_e}",',
        "        )",
        "    except Exception:",
        "        pass",
        END,
    ]
    return "\n".join(indent + ln if ln else ln for ln in lines) + "\n"


def _strip(text: str) -> str:
    return re.sub(
        rf"[ \t]*{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "",
        text,
    )


def _copy_helpers(root: Path) -> None:
    here = Path(__file__).resolve().parent
    for name in (
        "force_publish_public_snapshot.py",
        "viewer_publish_wake.py",
        "race_course_distance.py",
        "race_pace_label.py",
    ):
        src = here / name
        dst = root / name
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)


def patch(root: Path) -> None:
    root = root.resolve()
    worker = root / WORKER_NAME
    if not worker.is_file():
        raise SystemExit(f"missing {worker}")

    _copy_helpers(root)

    text = worker.read_text(encoding="utf-8", errors="replace")
    text = _strip(text)

    # 本日成功パスのアンカー: キャッシュ更新直後（通知の前）
    m = re.search(
        r"(?m)^(?P<ind>[ \t]*)update_races_cache_entry\(\s*rid\s*,\s*rblob\s*\)\s*\n",
        text,
    )
    if not m:
        raise SystemExit("anchor update_races_cache_entry(rid, rblob) not found")

    indent = m.group("ind")
    insert_at = m.end()

    window = text[max(0, m.start() - 80) : m.end() + 600]
    if BEGIN in text:
        pass
    elif "_publish_public_viewer_snapshot" in window or "run_publish" in window:
        print("publish call already present near update_races_cache_entry; skip inject")
        worker.write_text(text, encoding="utf-8")
        return

    bak = worker.with_suffix(worker.suffix + ".bak_publish_on_success")
    if not bak.exists():
        shutil.copy2(worker, bak)
        print(f"backup {bak}")

    updated = text[:insert_at] + _inject_block(indent) + text[insert_at:]
    worker.write_text(updated, encoding="utf-8")
    print(f"patched {worker}")


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x")
    patch(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

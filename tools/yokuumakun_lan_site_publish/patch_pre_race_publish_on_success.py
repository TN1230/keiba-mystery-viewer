#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pre_race_auto_predict_worker.py の成功パスで公開 snapshot を publish するようパッチする。

本日(2026-08-01)の成功パターン:
  発走約15分前 → 予想OK → update_races_cache_entry(rid, rblob) → (通知)
公開 latest.json は札幌9R(pred 14:05)まで追いついた後止まり、
札幌10R以降が朝一斉 predicted_at のまま残った。キャッシュ更新直後の
publish が欠落しているため、その直後に強制 publish を差し込む。
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
        "    try:",
        "        from force_publish_public_snapshot import run_publish as _force_pub",
        "        _pub = _force_pub(force=True)",
        "        try:",
        '            _dbg_morning_bulk_log(',
        '                "H7",',
        '                "pre_race_auto_predict_worker.py:main",',
        '                "public_viewer_publish",',
        '                {"race_id": rid, "result": str(_pub)[:240]},',
        "            )",
        "        except Exception:",
        "            pass",
        "    except Exception:",
        "        from hwm import _publish_public_viewer_snapshot",
        "        _publish_public_viewer_snapshot(force=True)",
        "        try:",
        '            _dbg_morning_bulk_log(',
        '                "H7",',
        '                "pre_race_auto_predict_worker.py:main",',
        '                "public_viewer_publish_hwm",',
        '                {"race_id": rid},',
        "            )",
        "        except Exception:",
        "            pass",
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
        END,
    ]
    return "\n".join(indent + ln if ln else ln for ln in lines) + "\n"


def _strip(text: str) -> str:
    return re.sub(
        rf"[ \t]*{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "",
        text,
    )


def patch(root: Path) -> None:
    root = root.resolve()
    worker = root / WORKER_NAME
    if not worker.is_file():
        raise SystemExit(f"missing {worker}")

    src = Path(__file__).resolve().parent / "force_publish_public_snapshot.py"
    dst = root / "force_publish_public_snapshot.py"
    if src.is_file() and src.resolve() != dst.resolve():
        shutil.copy2(src, dst)

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
        # already patched after strip shouldn't happen; re-inject below
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

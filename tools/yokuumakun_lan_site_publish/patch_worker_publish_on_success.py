#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""morning_bulk_server_worker.py の品質OK完了時に公開 snapshot を publish するようパッチする。"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN morning_bulk_publish_on_success"
END = "# END morning_bulk_publish_on_success"

def _inject_block(indent: str) -> str:
    lines = [
        BEGIN,
        "try:",
        '    _log("publishing public viewer snapshot after quality ok")',
        "    try:",
        "        from force_publish_public_snapshot import run_publish as _force_pub",
        "        _pub = _force_pub(force=True)",
        '        _log(f"publish result={_pub}")',
        "    except Exception:",
        "        from hwm import _publish_public_viewer_snapshot",
        "        _publish_public_viewer_snapshot(force=True)",
        '        _log("publish via hwm._publish_public_viewer_snapshot ok")',
        "except Exception as _pub_e:",
        '    _log(f"publish failed: {type(_pub_e).__name__}: {_pub_e}")',
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
    worker = root / "morning_bulk_server_worker.py"
    if not worker.is_file():
        raise SystemExit(f"missing {worker}")

    # force_publish スクリプトをルートへ（既に同ファイルならスキップ）
    src = Path(__file__).resolve().parent / "force_publish_public_snapshot.py"
    dst = root / "force_publish_public_snapshot.py"
    if src.is_file() and src.resolve() != dst.resolve():
        shutil.copy2(src, dst)

    text = worker.read_text(encoding="utf-8", errors="replace")
    text = _strip(text)

    # quality OK の mark done の直後に挿入
    m = re.search(
        r"(?m)^(?P<ind>[ \t]*)_mark_morning_bulk_done_on_disk\([^\n]+\)\s*\n",
        text,
    )
    if not m:
        raise SystemExit("anchor _mark_morning_bulk_done_on_disk not found")

    indent = m.group("ind")
    # mark の次の行が _log(done ok) ならその後、そうでなければ mark の直後
    insert_at = m.end()
    following = text[insert_at : insert_at + 240]
    mlog = re.match(r"(?m)^([ \t]*)_log\(f\"done ok[^\n]*\n", following)
    if mlog:
        insert_at = insert_at + mlog.end()

    # 既に publish 呼び出しがある場合は二重化を避ける（近傍チェック）
    window = text[max(0, m.start() - 100) : m.end() + 500]
    if "_publish_public_viewer_snapshot" in window or "run_publish" in window:
        if BEGIN not in text:
            print("publish call already present near mark done; skip inject")
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

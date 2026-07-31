#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ops_discord_notify.py に morning_bulk TEST_ALWAYS フィルタを組み込む。

使い方（サーバー上で）:
  python3 install_into_ops_discord_notify.py /opt/yokuumakun_auto-x
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN = "# BEGIN morning_bulk_test_webhook_filter"
END = "# END morning_bulk_test_webhook_filter"

INJECT_BLOCK = f"""
{BEGIN}
try:
    from morning_bulk_test_webhook_filter import apply_to_ops_module as _mb_tw_apply

    _mb_tw_apply(sys.modules[__name__])
except Exception:
    pass
{END}
"""


def _ensure_sys_import(text: str) -> str:
    if re.search(r"(?m)^\s*import\s+sys\s*$", text):
        return text
    # from __future__ の直後、または先頭 import 群の前に追加
    m = re.search(r"(?m)^(from __future__ import .+\n)", text)
    if m:
        return text[: m.end()] + "import sys\n" + text[m.end() :]
    m = re.search(r"(?m)^(import |from )", text)
    if m:
        return text[: m.start()] + "import sys\n" + text[m.start() :]
    return "import sys\n" + text


def _strip_previous_inject(text: str) -> str:
    return re.sub(
        rf"\n?{re.escape(BEGIN)}[\s\S]*?{re.escape(END)}\n?",
        "\n",
        text,
        count=1,
    )


def _insert_inject(text: str) -> str:
    text = _strip_previous_inject(text)
    text = _ensure_sys_import(text)
    # notify_action 定義の直後に挿入（関数本体の外）
    m = re.search(r"(?m)^def notify_action\s*\(", text)
    if not m:
        raise RuntimeError("def notify_action( not found in ops_discord_notify.py")
    # 次のトップレベル def/class か EOF まで飛ばして、notify_action ブロックの後ろに入れる
    rest = text[m.start() :]
    # 簡易: 次の「行頭 def / class」を探す（notify_action 自身を除く）
    m2 = re.search(r"(?m)^(?:def |class )", rest[1:])
    if m2:
        insert_at = m.start() + 1 + m2.start()
        return text[:insert_at] + INJECT_BLOCK + "\n" + text[insert_at:]
    # ファイル末尾
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + INJECT_BLOCK + "\n"


def install(root: Path) -> None:
    root = root.resolve()
    src_filter = Path(__file__).resolve().parent / "morning_bulk_test_webhook_filter.py"
    if not src_filter.is_file():
        raise SystemExit(f"missing {src_filter}")

    dest_filter = root / "morning_bulk_test_webhook_filter.py"
    shutil.copy2(src_filter, dest_filter)
    print(f"copied {dest_filter}")

    ops = root / "ops_discord_notify.py"
    if not ops.is_file():
        raise SystemExit(f"missing {ops}")

    bak = ops.with_suffix(ops.suffix + ".bak_mb_tw_filter")
    if not bak.exists():
        shutil.copy2(ops, bak)
        print(f"backup {bak}")

    original = ops.read_text(encoding="utf-8", errors="replace")
    updated = _insert_inject(original)
    if updated == original and BEGIN in original:
        # 再適用: ブロック差し替え済みなら filter ファイル更新だけでよい
        print("inject already present; refreshed filter module only")
        # それでもブロックを最新内容に更新
        updated = _insert_inject(original)
    ops.write_text(updated, encoding="utf-8")
    print(f"patched {ops}")


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x")
    install(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

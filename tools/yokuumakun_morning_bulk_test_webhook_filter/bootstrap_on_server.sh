#!/usr/bin/env bash
# サーバー上で実行: GitHub から取得して ops_discord_notify にフィルタを組み込む
# 例:
#   bash bootstrap_on_server.sh
#   bash bootstrap_on_server.sh cursor/morning-bulk-test-webhook-filter-19c2
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/morning-bulk-test-webhook-filter-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_morning_bulk_test_webhook_filter"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

cd "$TMP"
curl -fsSL -o morning_bulk_test_webhook_filter.py "$BASE/morning_bulk_test_webhook_filter.py"
curl -fsSL -o install_into_ops_discord_notify.py "$BASE/install_into_ops_discord_notify.py"
python3 install_into_ops_discord_notify.py "$ROOT"

cd "$ROOT"
.venv/bin/python -m py_compile morning_bulk_test_webhook_filter.py ops_discord_notify.py

# 動作確認（TEST_ALWAYS が中間イベントで消えること）
.venv/bin/python - <<'PY'
import os
import sys
sys.path.insert(0, ".")
os.environ.setdefault("DISCORD_NOTIFY_ON", "0")  # 実送信オフ（可能な実装向け）
from morning_bulk_test_webhook_filter import allow_morning_bulk_test_always
assert allow_morning_bulk_test_always("morning_bulk_worker_start", "ok")
assert allow_morning_bulk_test_always("morning_bulk_worker_done", "ok")
assert allow_morning_bulk_test_always("morning_bulk_worker_fatal", "error")
assert not allow_morning_bulk_test_always("morning_bulk_cache_flush", "ok")
import ops_discord_notify as odn
fn = odn.notify_action
assert getattr(fn, "morning_bulk_test_webhook_filter", False), fn
assert getattr(fn, "__wrapped__", None) is not None
print("OK: morning_bulk TEST_ALWAYS filter active on", odn.__file__)
PY

echo "DONE: morning_bulk test-webhook filter installed (no service restart required for next notify_action import)"

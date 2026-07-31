#!/usr/bin/env bash
# サーバー上で実行: GitHub から最新ツールを取得して admin API に組み込む
# 例:
#   DISCORD_WEBHOOK_TEST='https://discord.com/api/webhooks/...' bash bootstrap_on_server.sh
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/admin-netkeiba-access-test-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_netkeiba_access_test"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

cd "$TMP"
curl -fsSL -o netkeiba_access_test.py "$BASE/netkeiba_access_test.py"
curl -fsSL -o install_into_admin_panel.py "$BASE/install_into_admin_panel.py"
python3 install_into_admin_panel.py "$ROOT"

cd "$ROOT"
.venv/bin/python -m py_compile netkeiba_access_test.py admin_panel_api.py

ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"
if [[ -n "${DISCORD_WEBHOOK_TEST:-}" ]]; then
  # 既存キーを置換、なければ追記（値はシェル経由のみ。リポジトリには書かない）
  if grep -q '^DISCORD_WEBHOOK_TEST=' "$ENV_FILE"; then
    python3 - <<PY
from pathlib import Path
p = Path("$ENV_FILE")
lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
out = []
for line in lines:
    if line.startswith("DISCORD_WEBHOOK_TEST="):
        out.append("DISCORD_WEBHOOK_TEST=" + __import__("os").environ["DISCORD_WEBHOOK_TEST"])
    else:
        out.append(line)
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("updated DISCORD_WEBHOOK_TEST in .env")
PY
  else
    printf 'DISCORD_WEBHOOK_TEST=%s\n' "$DISCORD_WEBHOOK_TEST" >> "$ENV_FILE"
    echo "appended DISCORD_WEBHOOK_TEST to .env"
  fi
elif ! grep -q '^DISCORD_WEBHOOK_TEST=' "$ENV_FILE" 2>/dev/null; then
  echo '# DISCORD_WEBHOOK_TEST=https://discord.com/api/webhooks/...' >> "$ENV_FILE"
  echo "NOTE: set DISCORD_WEBHOOK_TEST in $ENV_FILE"
fi

sudo systemctl restart yokuum-admin-panel.service
sleep 1
systemctl is-active yokuum-admin-panel.service
curl -sS http://127.0.0.1:8791/health
echo

# インストール後の疎通（Webhook 通知まで）
if [[ -n "${DISCORD_WEBHOOK_TEST:-}" ]]; then
  export DISCORD_WEBHOOK_TEST
  export YOKUMAKUN_ROOT="$ROOT"
  "$ROOT/.venv/bin/python" - <<'PY'
from netkeiba_access_test import run_netkeiba_access_test
import json
r = run_netkeiba_access_test()
print(json.dumps({k: r.get(k) for k in ("ok", "denied", "race_id", "message", "webhook")}, ensure_ascii=False))
raise SystemExit(0 if r.get("ok") and (r.get("webhook") or {}).get("ok") else 1)
PY
fi

echo "DONE: POST /admin/netkeiba-access-test is ready"

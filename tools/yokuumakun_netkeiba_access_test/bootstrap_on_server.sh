#!/usr/bin/env bash
# サーバー上で実行: GitHub から最新ツールを取得して admin API に組み込む
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/admin-netkeiba-access-test-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_netkeiba_access_test"
TMP="$(mktemp -d)"
cd "$TMP"
curl -fsSL -o netkeiba_access_test.py "$BASE/netkeiba_access_test.py"
curl -fsSL -o install_into_admin_panel.py "$BASE/install_into_admin_panel.py"
python3 install_into_admin_panel.py "$ROOT"
cd "$ROOT"
.venv/bin/python -m py_compile netkeiba_access_test.py admin_panel_api.py
if ! grep -q '^DISCORD_WEBHOOK_TEST=' .env 2>/dev/null; then
  echo '# DISCORD_WEBHOOK_TEST=https://discord.com/api/webhooks/...' >> .env
  echo "NOTE: set DISCORD_WEBHOOK_TEST in $ROOT/.env"
fi
sudo systemctl restart yokuum-admin-panel.service
sleep 1
systemctl is-active yokuum-admin-panel.service
curl -sS http://127.0.0.1:8791/health
echo
echo "DONE: POST /admin/netkeiba-access-test is ready"

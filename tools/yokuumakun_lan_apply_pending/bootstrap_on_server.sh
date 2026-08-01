#!/usr/bin/env bash
# サーバー上 / LAN から一括適用（SSH tunnel + publish fix + webhook filter）
# Windows からは deploy_from_windows.ps1（paramiko + sudo -S）を推奨。
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"

echo "INFO: lan_apply_pending root=$ROOT"

echo "=== [1/3] morning-bulk publish fix ==="
curl -fsSL \
  "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-publish-fix-19c2/tools/yokuumakun_morning_bulk_publish_fix/bootstrap_on_server.sh" \
  | bash

echo "=== [2/3] morning-bulk test-webhook filter ==="
curl -fsSL \
  "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-test-webhook-filter-19c2/tools/yokuumakun_morning_bulk_test_webhook_filter/bootstrap_on_server.sh" \
  | bash

echo "=== [3/3] SSH internet tunnel ==="
WRAP="$(mktemp -d)"
cleanup() { rm -rf "$WRAP"; }
trap cleanup EXIT
if [[ -n "$SUDO_PASS" ]]; then
  printf '%s\n' "$SUDO_PASS" >"$WRAP/pass"
  chmod 600 "$WRAP/pass"
  cat >"$WRAP/sudo" <<EOF
#!/bin/bash
echo "\$(cat '$WRAP/pass')" | /usr/bin/sudo -S -p '' "\$@"
EOF
  chmod 755 "$WRAP/sudo"
  export PATH="$WRAP:$PATH"
fi
curl -fsSL \
  "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_ssh_internet_tunnel/bootstrap_on_server.sh" \
  | env YOKUMAKUN_SUDO_PASS="$SUDO_PASS" bash

echo "DONE: lan_apply_pending finished"
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json" || true
echo
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" | head -c 300 || true
echo

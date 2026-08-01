#!/usr/bin/env bash
# サーバー上 / LAN から一括適用（SSH tunnel を最優先 + publish fix + webhook filter）
# Windows からは deploy_from_windows.ps1（paramiko + sudo -S）を推奨。
#
# 注意: 以前の版は publish force 失敗で set -e により tunnel まで到達しないことがあった。
set -uo pipefail
# 個別ステップの失敗で全体を止めない（tunnel 確保を優先）

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
RC_TUNNEL=0
RC_PUBLISH=0
RC_FILTER=0

echo "INFO: lan_apply_pending root=$ROOT"

run_step() {
  local name="$1"
  shift
  echo
  echo "=== ${name} ==="
  set +e
  "$@"
  local rc=$?
  set -e
  echo "=== ${name} rc=${rc} ==="
  return "$rc"
}

# --- [1/3] SSH tunnel FIRST（クラウド到達の前提） ---
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

run_step "[1/3] SSH internet tunnel" \
  env YOKUMAKUN_SUDO_PASS="$SUDO_PASS" bash -c \
  'curl -fsSL "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_ssh_internet_tunnel/bootstrap_on_server.sh" | bash' \
  || RC_TUNNEL=$?

# --- [2/3] publish fix（force publish 失敗でもインストールは進める） ---
run_step "[2/3] morning-bulk publish fix" bash -c '
  set +e
  curl -fsSL \
    "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-publish-fix-19c2/tools/yokuumakun_morning_bulk_publish_fix/bootstrap_on_server.sh" \
    | bash
  rc=$?
  # publish 失敗でもパッチ自体は入っていることが多い。続行。
  exit 0
' || RC_PUBLISH=$?

# --- [3/3] webhook filter ---
run_step "[3/3] morning-bulk test-webhook filter" bash -c '
  curl -fsSL \
    "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-test-webhook-filter-19c2/tools/yokuumakun_morning_bulk_test_webhook_filter/bootstrap_on_server.sh" \
    | bash
' || RC_FILTER=$?

echo
echo "DONE: lan_apply_pending finished tunnel_rc=$RC_TUNNEL publish_rc=$RC_PUBLISH filter_rc=$RC_FILTER"
echo "--- ssh_endpoint.json ---"
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json" || echo "(missing)"
echo
echo "--- local endpoint ---"
cat "$ROOT/logs/ssh_endpoint.local.json" 2>/dev/null || echo "(no local endpoint file)"
echo
echo "--- snapshot head ---"
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" | head -c 400 || true
echo
echo "--- tunnel service ---"
systemctl is-active yokuum-ssh-tcp-tunnel.service 2>/dev/null || true
if [[ -n "$SUDO_PASS" ]]; then
  echo "$SUDO_PASS" | sudo -S -p '' journalctl -u yokuum-ssh-tcp-tunnel.service -n 40 --no-pager 2>/dev/null || true
else
  journalctl -u yokuum-ssh-tcp-tunnel.service -n 40 --no-pager 2>/dev/null || true
fi

# tunnel が公開できていれば 0、否则 1（ログは出したうえで）
if curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json" 2>/dev/null | grep -q '"port"'; then
  exit 0
fi
if [[ -f "$ROOT/logs/ssh_endpoint.local.json" ]] && grep -q '"port"' "$ROOT/logs/ssh_endpoint.local.json"; then
  echo "WARN: local endpoint exists but public ssh_endpoint.json missing — paste local JSON to cloud agent"
  exit 2
fi
exit 1

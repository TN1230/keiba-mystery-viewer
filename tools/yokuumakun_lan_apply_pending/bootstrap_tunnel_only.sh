#!/usr/bin/env bash
set -euo pipefail
export YOKUMAKUN_SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
URL="${1:-https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-bore-endpoint-a29c/tools/yokuumakun_lan_apply_pending/bootstrap_tunnel_embedded.sh}"
curl -fsSL "$URL" | env YOKUMAKUN_SUDO_PASS="$YOKUMAKUN_SUDO_PASS" bash | tee /tmp/ssh_tunnel_only.log

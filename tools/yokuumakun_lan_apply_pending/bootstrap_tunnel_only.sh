#!/usr/bin/env bash
set -euo pipefail
export YOKUMAKUN_SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
URL="${1:-https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@987c8c3e95421203fa21fa03b19ebe0421ffdc1a/tools/yokuumakun_lan_apply_pending/bootstrap_tunnel_embedded.sh}"
curl -fsSL "$URL" | env YOKUMAKUN_SUDO_PASS="$YOKUMAKUN_SUDO_PASS" bash | tee /tmp/ssh_tunnel_only.log

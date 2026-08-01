#!/usr/bin/env bash
# SSH tunnel だけを入れる（最短）。publish 失敗の影響を受けない。
set -euo pipefail
export YOKUMAKUN_SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
curl -fsSL \
  "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_ssh_internet_tunnel/bootstrap_on_server.sh" \
  | env YOKUMAKUN_SUDO_PASS="$YOKUMAKUN_SUDO_PASS" bash | tee /tmp/ssh_tunnel_only.log

#!/usr/bin/env bash
# SSH tunnel だけ（埋め込み版を jsDelivr 経由で実行 — raw ブランチキャッシュを回避）
set -euo pipefail
export YOKUMAKUN_SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
URL="${1:-https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_lan_apply_pending/bootstrap_tunnel_embedded.sh}"
curl -fsSL "$URL" | env YOKUMAKUN_SUDO_PASS="$YOKUMAKUN_SUDO_PASS" bash | tee /tmp/ssh_tunnel_only.log

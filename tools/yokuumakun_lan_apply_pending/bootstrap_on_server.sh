#!/usr/bin/env bash
# 一括適用（埋め込み tunnel 優先 → publish fix → webhook filter）
# CDN キャッシュ回避のため tunnel は同梱埋め込みスクリプトを使う。
set -uo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
# ピン留め（raw ブランチURLのキャッシュ踏み抜き）
PUB_REF="${YOKUMAKUN_PUBLISH_REF:-25405d13554922453479d50565d11e52b3fd7519}"
FILTER_REF="${YOKUMAKUN_FILTER_REF:-58ccef1fe949acf32aa0cf5633cf0b9a5ebea974}"
TUNNEL_REF="${YOKUMAKUN_TUNNEL_REF:-}"  # 空なら同ディレクトリの embedded を優先

echo "INFO: lan_apply_pending root=$ROOT"

run_step() {
  local name="$1"; shift
  echo; echo "=== ${name} ==="
  set +e
  "$@"
  local rc=$?
  set +e
  echo "=== ${name} rc=${rc} ==="
  return "$rc"
}

# [1] tunnel — embedded（同梱）を curl 経由でも取れるように GitHub から取得
EMBED_URL_JS="https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@987c8c3e95421203fa21fa03b19ebe0421ffdc1a/tools/yokuumakun_lan_apply_pending/bootstrap_tunnel_embedded.sh"
# jsDelivr branch tip; also try commit if set
if [[ -n "$TUNNEL_REF" ]]; then
  EMBED_URL_JS="https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${TUNNEL_REF}/tools/yokuumakun_lan_apply_pending/bootstrap_tunnel_embedded.sh"
fi

run_step "[1/3] SSH tunnel (embedded)" bash -c "
  export YOKUMAKUN_SUDO_PASS=$(printf %q "$SUDO_PASS")
  export YOKUMAKUN_SSH_PASS=$(printf %q "$SUDO_PASS")
  curl -fsSL '$EMBED_URL_JS' | bash
" || true

# [2] publish fix — 失敗しても続行
run_step "[2/3] publish fix" bash -c "
  export YOKUMAKUN_SUDO_PASS=$(printf %q "$SUDO_PASS")
  curl -fsSL 'https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${PUB_REF}/tools/yokuumakun_morning_bulk_publish_fix/bootstrap_on_server.sh' | bash
  exit 0
" || true

# [3] webhook filter
run_step "[3/3] webhook filter" bash -c "
  curl -fsSL 'https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${FILTER_REF}/tools/yokuumakun_morning_bulk_test_webhook_filter/bootstrap_on_server.sh' | bash
" || true

echo
echo "DONE lan_apply_pending"
echo "--- ssh_endpoint ---"
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json" || echo "(missing)"
echo
cat "$ROOT/logs/ssh_endpoint.local.json" 2>/dev/null || true
echo
echo "--- snapshot ---"
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" | head -c 400 || true
echo
if curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json" 2>/dev/null | grep -q '"port"'; then
  exit 0
fi
exit 1

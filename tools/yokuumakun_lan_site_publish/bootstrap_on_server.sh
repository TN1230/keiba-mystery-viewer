#!/usr/bin/env bash
# 自宅サーバー上で実行:
#  1) 今すぐ latest.json を強制公開
#  2) 朝一斉成功時に自動 publish するよう worker を改修
#  3) 明日以降の保険として systemd timer を入れる
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/lan-site-publish-19c2}"
# raw + jsDelivr の両方を試し、キャッシュ踏み抜き
BASE_RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_lan_site_publish"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
export YOKUMAKUN_SUDO_PASS="$SUDO_PASS"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-$SUDO_PASS}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

sudo_run() {
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo "$@"
  fi
}

fetch() {
  local f="$1"
  if curl -fsSL -o "$f" "$BASE_RAW/$f"; then
    return 0
  fi
  curl -fsSL -o "$f" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${BRANCH}/tools/yokuumakun_lan_site_publish/$f"
}

echo "INFO: lan site publish bootstrap root=$ROOT branch=$BRANCH"
cd "$TMP"
for f in \
  force_publish_public_snapshot.py \
  patch_worker_publish_on_success.py \
  install_publish_endpoint.py \
  install_remote_bootstrap_endpoint.py \
  morning_bulk_publish_watch.py \
  install_daily_publish_watch.py \
  yokuum-morning-publish-watch.service.example \
  yokuum-morning-publish-watch.timer.example
do
  echo "INFO: download $f"
  fetch "$f"
done

python3 patch_worker_publish_on_success.py "$ROOT"
python3 install_publish_endpoint.py "$ROOT"
python3 install_remote_bootstrap_endpoint.py "$ROOT" || true
cp -f force_publish_public_snapshot.py morning_bulk_publish_watch.py "$ROOT/"
cp -f yokuum-morning-publish-watch.service.example yokuum-morning-publish-watch.timer.example "$ROOT/server_deployment/" 2>/dev/null || {
  mkdir -p "$ROOT/server_deployment"
  cp -f yokuum-morning-publish-watch.service.example yokuum-morning-publish-watch.timer.example "$ROOT/server_deployment/"
}

cd "$ROOT"
.venv/bin/python -m py_compile \
  force_publish_public_snapshot.py \
  morning_bulk_publish_watch.py \
  morning_bulk_server_worker.py \
  admin_panel_api.py

echo "=== force publish now ==="
set +e
.venv/bin/python force_publish_public_snapshot.py
PUB_RC=$?
set -e

echo "=== install daily publish watch timer ==="
set +e
python3 "$TMP/install_daily_publish_watch.py" "$ROOT"
TIMER_RC=$?
set -e

if systemctl is-active --quiet yokuum-admin-panel.service 2>/dev/null; then
  sudo_run systemctl restart yokuum-admin-panel.service || true
  sleep 1
  curl -sS http://127.0.0.1:8791/health || true
  echo
fi

echo "=== timer status ==="
systemctl is-enabled yokuum-morning-publish-watch.timer 2>/dev/null || true
systemctl list-timers yokuum-morning-publish-watch.timer --no-pager 2>/dev/null || true

echo "=== latest.json ==="
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" | head -c 600
echo

if [[ "$PUB_RC" -ne 0 ]]; then
  echo "WARN: force publish rc=$PUB_RC (timer/worker patch may still be installed)"
fi
if [[ "$TIMER_RC" -ne 0 ]]; then
  echo "WARN: timer install rc=$TIMER_RC"
fi
if [[ "$PUB_RC" -ne 0 ]]; then
  exit "$PUB_RC"
fi
echo "DONE: site published + worker publish-on-success + daily timer"

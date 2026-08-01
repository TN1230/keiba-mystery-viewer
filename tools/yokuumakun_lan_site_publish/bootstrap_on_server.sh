#!/usr/bin/env bash
# 自宅サーバー上で実行: 閲覧サイト latest.json を強制公開 + 今後の一斉予想成功時も自動公開
# （クラウド / bore 不要。先週のサーバー直実行と同じ系統）
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/lan-site-publish-19c2}"
BASE="https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${BRANCH}/tools/yokuumakun_lan_site_publish"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
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

cd "$TMP"
for f in force_publish_public_snapshot.py patch_worker_publish_on_success.py install_publish_endpoint.py install_remote_bootstrap_endpoint.py; do
  curl -fsSL -o "$f" "$BASE/$f"
done

python3 patch_worker_publish_on_success.py "$ROOT"
python3 install_publish_endpoint.py "$ROOT"
python3 install_remote_bootstrap_endpoint.py "$ROOT" || true
cp force_publish_public_snapshot.py "$ROOT/"

cd "$ROOT"
.venv/bin/python -m py_compile \
  force_publish_public_snapshot.py \
  morning_bulk_server_worker.py \
  admin_panel_api.py

echo "=== force publish now ==="
set +e
.venv/bin/python force_publish_public_snapshot.py
PUB_RC=$?
set -e

if systemctl is-active --quiet yokuum-admin-panel.service 2>/dev/null; then
  sudo_run systemctl restart yokuum-admin-panel.service || true
  sleep 1
  curl -sS http://127.0.0.1:8791/health || true
  echo
fi

echo "=== latest.json ==="
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" | head -c 500
echo

if [[ "$PUB_RC" -ne 0 ]]; then
  echo "WARN: force publish rc=$PUB_RC"
  exit "$PUB_RC"
fi
echo "DONE: site publish + worker publish-on-success installed"

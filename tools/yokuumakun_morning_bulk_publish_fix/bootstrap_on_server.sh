#!/usr/bin/env bash
# サーバー上で実行: 公開漏れ修正を入れ、キャッシュから即 publish する
# 例:
#   curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-publish-fix-19c2/tools/yokuumakun_morning_bulk_publish_fix/bootstrap_on_server.sh | bash
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/morning-bulk-publish-fix-19c2}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
sudo_run() {
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo "$@"
  fi
}
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_morning_bulk_publish_fix"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

cd "$TMP"
for f in force_publish_public_snapshot.py patch_worker_publish_on_success.py install_publish_endpoint.py install_remote_bootstrap_endpoint.py; do
  curl -fsSL -o "$f" "$BASE/$f"
done

python3 patch_worker_publish_on_success.py "$ROOT"
python3 install_publish_endpoint.py "$ROOT"
python3 install_remote_bootstrap_endpoint.py "$ROOT" || true

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

# admin API にエンドポイントを載せる（KillMode=process 想定で worker は生き残る）
if systemctl is-active --quiet yokuum-admin-panel.service 2>/dev/null; then
  sudo_run systemctl restart yokuum-admin-panel.service || true
  sleep 1
  systemctl is-active yokuum-admin-panel.service || true
  curl -sS http://127.0.0.1:8791/health || true
  echo
fi

if [[ "$PUB_RC" -ne 0 ]]; then
  echo "WARN: force publish returned $PUB_RC — patches installed; continuing"
else
  echo "DONE: worker publish-on-success + admin /admin/publish-public-snapshot + forced publish"
fi
exit 0

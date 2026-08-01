#!/usr/bin/env bash
# 自宅サーバー上で実行:
#  1) 今すぐ latest.json を強制公開（最優先・パッチ失敗でも実施）
#  2) 朝一斉成功時に自動 publish するよう worker を改修
#  3) 明日以降の保険として systemd timer を入れる
set -uo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/lan-site-publish-19c2}"
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
echo "INFO: diagnostic logs pkl/flags:"
ls -lt "$ROOT/logs"/morning_bulk_races_*.pkl 2>/dev/null | head -10 || echo "(no pkl)"
ls -lt "$ROOT/logs"/morning_bulk_done_*.flag 2>/dev/null | head -10 || echo "(no done flags)"

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
  fetch "$f" || echo "WARN: download failed $f"
done

# --- 最優先: 今すぐ公開（パッチ前） ---
cp -f force_publish_public_snapshot.py "$ROOT/" 2>/dev/null || true
echo "=== force publish NOW (before patches) ==="
set +e
cd "$ROOT"
.venv/bin/python force_publish_public_snapshot.py
PUB_RC=$?
set -e
echo "force_publish rc=$PUB_RC"

# --- 恒久パッチ ---
echo "=== install lasting patches ==="
set +e
python3 "$TMP/patch_worker_publish_on_success.py" "$ROOT"
echo "patch_worker rc=$?"
python3 "$TMP/install_publish_endpoint.py" "$ROOT"
echo "install_publish_endpoint rc=$?"
python3 "$TMP/install_remote_bootstrap_endpoint.py" "$ROOT"
echo "install_remote_bootstrap rc=$?"
cp -f "$TMP/morning_bulk_publish_watch.py" "$ROOT/" 2>/dev/null || true
mkdir -p "$ROOT/server_deployment"
cp -f "$TMP"/yokuum-morning-publish-watch.*.example "$ROOT/server_deployment/" 2>/dev/null || true
cd "$ROOT"
.venv/bin/python -m py_compile force_publish_public_snapshot.py morning_bulk_publish_watch.py morning_bulk_server_worker.py admin_panel_api.py
echo "py_compile rc=$?"
python3 "$TMP/install_daily_publish_watch.py" "$ROOT"
echo "timer_install rc=$?"
set +e

# もう一度 publish（パッチ後の force_publish を使う）
echo "=== force publish AGAIN ==="
cd "$ROOT"
.venv/bin/python force_publish_public_snapshot.py
PUB_RC2=$?
echo "force_publish2 rc=$PUB_RC2"

if systemctl is-active --quiet yokuum-admin-panel.service 2>/dev/null; then
  sudo_run systemctl restart yokuum-admin-panel.service || true
  sleep 1
  curl -sS http://127.0.0.1:8791/health || true
  echo
fi

echo "=== timer ==="
systemctl is-enabled yokuum-morning-publish-watch.timer 2>/dev/null || true
systemctl list-timers 'yokuum-morning-publish-watch.timer' --no-pager 2>/dev/null || true

echo "=== latest.json ==="
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" | head -c 800
echo

if curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" 2>/dev/null | grep -q '"race_count": [1-9]'; then
  echo "DONE: site has races"
  exit 0
fi
echo "ERROR: latest.json still empty — paste /tmp/lan_site_publish.log"
echo "Also check: ls -lt $ROOT/logs/morning_bulk_races_*.pkl | head"
exit 1

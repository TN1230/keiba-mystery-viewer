#!/usr/bin/env bash
# 自宅サーバー上で実行:
#  1) 今すぐ latest.json を強制公開（最優先・パッチ失敗でも実施）
#  2) 朝一斉成功時に自動 publish するよう worker を改修
#  3) 明日以降の保険として systemd timer を入れる
set -uo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/race-summary-pace-label-19c2}"
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
  standalone_publish_from_cache.py \
  official_republish_from_cache.py \
  patch_worker_publish_on_success.py \
  patch_pre_race_publish_on_success.py \
  viewer_publish_wake.py \
  race_course_distance.py \
  race_pace_label.py \
  install_publish_endpoint.py \
  morning_bulk_publish_watch.py \
  install_daily_publish_watch.py \
  upload_bootstrap_status.py \
  yokuum-morning-publish-watch.service.example \
  yokuum-morning-publish-watch.timer.example
do
  echo "INFO: download $f"
  fetch "$f" || echo "WARN: download failed $f"
done

# admin が壊れている場合は先に戻す（公開より前）
if [[ -f "$ROOT/admin_panel_api.py" ]]; then
  if ! "$ROOT/.venv/bin/python" -m py_compile "$ROOT/admin_panel_api.py" 2>/dev/null; then
    echo "WARN: admin_panel_api.py broken — restoring backup before publish"
    if [[ -f "$ROOT/admin_panel_api.py.bak_publish_endpoint" ]]; then
      cp -f "$ROOT/admin_panel_api.py.bak_publish_endpoint" "$ROOT/admin_panel_api.py"
    fi
  fi
fi

# --- 最優先: 今すぐ公開（パッチ前） ---
cp -f force_publish_public_snapshot.py "$ROOT/" 2>/dev/null || true
cp -f standalone_publish_from_cache.py "$ROOT/" 2>/dev/null || true
echo "=== force publish NOW (before patches) ==="
set +e
cd "$ROOT"
.venv/bin/python force_publish_public_snapshot.py
PUB_RC=$?
echo "force_publish rc=$PUB_RC"
if [[ "$PUB_RC" -ne 0 ]]; then
  echo "=== standalone publish fallback ==="
  .venv/bin/python standalone_publish_from_cache.py
  echo "standalone rc=$?"
fi
set -e

# --- 恒久パッチ ---
echo "=== install lasting patches ==="
set +e
python3 "$TMP/patch_worker_publish_on_success.py" "$ROOT"
echo "patch_worker rc=$?"
python3 "$TMP/patch_pre_race_publish_on_success.py" "$ROOT"
echo "patch_pre_race rc=$?"
python3 "$TMP/install_publish_endpoint.py" "$ROOT"
echo "install_publish_endpoint rc=$?"
cp -f "$TMP/morning_bulk_publish_watch.py" "$ROOT/" 2>/dev/null || true
cp -f "$TMP/viewer_publish_wake.py" "$ROOT/" 2>/dev/null || true
cp -f "$TMP/race_course_distance.py" "$ROOT/" 2>/dev/null || true
cp -f "$TMP/race_pace_label.py" "$ROOT/" 2>/dev/null || true
mkdir -p "$ROOT/server_deployment"
cp -f "$TMP"/yokuum-morning-publish-watch.*.example "$ROOT/server_deployment/" 2>/dev/null || true
cd "$ROOT"
set +e
.venv/bin/python -m py_compile force_publish_public_snapshot.py morning_bulk_publish_watch.py viewer_publish_wake.py race_course_distance.py race_pace_label.py morning_bulk_server_worker.py pre_race_auto_predict_worker.py
echo "py_compile_tools rc=$?"
.venv/bin/python -m py_compile admin_panel_api.py
ADMIN_COMPILE=$?
echo "py_compile_admin rc=$ADMIN_COMPILE"
if [[ "$ADMIN_COMPILE" -ne 0 ]]; then
  echo "WARN: admin_panel_api.py indent/syntax broken — restoring backups"
  if [[ -f admin_panel_api.py.bak_publish_endpoint ]]; then
    cp -f admin_panel_api.py.bak_publish_endpoint admin_panel_api.py
    echo "restored from bak_publish_endpoint"
    python3 "$TMP/install_publish_endpoint.py" "$ROOT" || true
  fi
  .venv/bin/python -m py_compile admin_panel_api.py
  echo "py_compile_admin_after_restore rc=$?"
fi
python3 "$TMP/install_daily_publish_watch.py" "$ROOT"
echo "timer_install rc=$?"
set +e

# もう一度 publish（パッチ後の force_publish / standalone を使う）
echo "=== force publish AGAIN ==="
cd "$ROOT"
cp -f "$TMP/standalone_publish_from_cache.py" "$ROOT/" 2>/dev/null || true
.venv/bin/python force_publish_public_snapshot.py
PUB_RC2=$?
echo "force_publish2 rc=$PUB_RC2"
if [[ "$PUB_RC2" -ne 0 ]]; then
  echo "=== standalone publish fallback 2 ==="
  .venv/bin/python standalone_publish_from_cache.py
  echo "standalone2 rc=$?"
fi

if systemctl list-unit-files yokuum-admin-panel.service 2>/dev/null | grep -q yokuum-admin-panel; then
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

FINAL_RC=1
if curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" 2>/dev/null | grep -q '"race_count": [1-9]'; then
  echo "DONE: site has races"
  FINAL_RC=0
else
  echo "ERROR: latest.json still empty"
  echo "Also check: ls -lt $ROOT/logs/morning_bulk_races_*.pkl | head"
  FINAL_RC=1
fi

# 実行結果を公開JSONへ（次回クラウド側で原因確認できるようにする）
if [[ -f "$TMP/upload_bootstrap_status.py" ]]; then
  # tee 先のログがあればそれを、なければこの実行の journal 相当として /tmp を使う
  STATUS_LOG="/tmp/lan_site_publish.log"
  if [[ ! -f "$STATUS_LOG" ]]; then
    STATUS_LOG="/tmp/lan_site_publish_inline.log"
    # 最低限の状態を残す
    {
      echo "inline status $(date -Iseconds)"
      ls -lt "$ROOT/logs"/morning_bulk_races_*.pkl 2>/dev/null | head -20 || true
      ls -lt "$ROOT/logs"/morning_bulk_done_*.flag 2>/dev/null | head -20 || true
    } >"$STATUS_LOG"
  fi
  python3 "$TMP/upload_bootstrap_status.py" --root "$ROOT" --log "$STATUS_LOG" --rc "$FINAL_RC" || true
fi
exit "$FINAL_RC"

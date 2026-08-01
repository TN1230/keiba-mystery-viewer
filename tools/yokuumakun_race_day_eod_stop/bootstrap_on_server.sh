#!/usr/bin/env bash
# サーバー上で実行: JST EOD 自己停止ガード + race_day_stop の cron/sudo 修正
# 例:
#   export YOKUMAKUN_SUDO_PASS='…'
#   bash bootstrap_on_server.sh
#   bash bootstrap_on_server.sh cursor/race-day-eod-jst-stop-guard-19c2
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/race-day-eod-jst-stop-guard-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_race_day_eod_stop"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

sudo_run() {
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo -n "$@" 2>/dev/null || sudo "$@"
  fi
}

fetch() {
  local f="$1"
  if curl -fsSL -o "$f" "$BASE/$f"; then
    return 0
  fi
  curl -fsSL -o "$f" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${BRANCH}/tools/yokuumakun_race_day_eod_stop/$f"
}

echo "INFO: race-day EOD stop bootstrap root=$ROOT branch=$BRANCH"
echo "INFO: system time: $(TZ=Asia/Tokyo date -Iseconds) (forced TZ=Asia/Tokyo for display)"
timedatectl 2>/dev/null | grep -i 'Time zone' || true

cd "$TMP"
fetch patch_automation_jst_eod_guard.py
fetch patch_race_day_stop_sudo_sys.py
fetch ensure_race_day_stop_cron.sh
chmod +x ensure_race_day_stop_cron.sh

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

echo "INFO: patch automation JST EOD guard"
"$PY" patch_automation_jst_eod_guard.py "$ROOT" || true

echo "INFO: patch race_day_stop sudo_sys"
"$PY" patch_race_day_stop_sudo_sys.py "$ROOT" || true

echo "INFO: ensure 20:00 cron"
bash ensure_race_day_stop_cron.sh

# すでに 20:00 JST を過ぎていれば即停止を試みる
HOUR="$(TZ=Asia/Tokyo date +%H)"
if [[ "$HOUR" -ge 20 ]]; then
  echo "WARN: already past 20:00 JST — running race_day_stop_hwm.sh now"
  STOP="${ROOT}/server_deployment/race_day_stop_hwm.sh"
  [[ -f "$STOP" ]] || STOP="${ROOT}/race_day_stop_hwm.sh"
  if [[ -f "$STOP" ]]; then
    export YOKUMAKUN_ROOT="$ROOT"
    export YOKUMAKUN_SUDO_PASS="${SUDO_PASS}"
    bash "$STOP" || true
  else
    echo "WARN: stop script missing; falling back to systemctl stop"
    sudo_run systemctl stop yokuum-server-automation-x.service || true
  fi
else
  echo "INFO: before 20:00 JST — cron will stop at 20:00"
fi

echo "INFO: automation state: $(systemctl is-active yokuum-server-automation-x.service 2>/dev/null || echo unknown)"
echo "DONE: race-day EOD stop hardening installed"

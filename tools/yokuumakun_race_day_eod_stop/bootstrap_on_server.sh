#!/usr/bin/env bash
# サーバー上で実行: 次回以降 毎日 20:00 JST に自動 stop するよう恒久設定
# 例:
#   export YOKUMAKUN_SUDO_PASS='…'
#   # 任意: サーバー .env にも YOKUMAKUN_SUDO_PASS を書いておく（推奨）
#   bash bootstrap_on_server.sh
#   bash bootstrap_on_server.sh cursor/race-day-timetable-guard-19c2
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/race-day-timetable-guard-19c2}"
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

CACHE_BUST="$(date +%s)"
fetch() {
  local f="$1"
  if curl -fsSL -o "$f" "${BASE}/${f}?t=${CACHE_BUST}"; then
    return 0
  fi
  curl -fsSL -o "$f" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${BRANCH}/tools/yokuumakun_race_day_eod_stop/${f}"
}

persist_sudo_pass_to_env() {
  # 次回以降 cron/timer が読めるよう .env に SUDO_PASS を残す（未設定時のみ追記）
  [[ -n "$SUDO_PASS" ]] || return 0
  local envf="${ROOT}/.env"
  mkdir -p "$ROOT"
  touch "$envf"
  if grep -qE '^YOKUMAKUN_SUDO_PASS=' "$envf" 2>/dev/null; then
    echo "INFO: YOKUMAKUN_SUDO_PASS already present in $envf"
  else
    printf '\n# used by race_day_stop (cron/systemd, non-interactive sudo)\nYOKUMAKUN_SUDO_PASS=%s\n' "$SUDO_PASS" >>"$envf"
    chmod 600 "$envf" || true
    echo "INFO: appended YOKUMAKUN_SUDO_PASS to $envf"
  fi
}

echo "INFO: race-day EOD stop bootstrap root=$ROOT branch=$BRANCH"
echo "INFO: system time: $(TZ=Asia/Tokyo date -Iseconds) (forced TZ=Asia/Tokyo for display)"
timedatectl 2>/dev/null | grep -i 'Time zone' || true

LAN_BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_lan_site_publish"
fetch_lan() {
  local f="$1"
  if curl -fsSL -o "$f" "$LAN_BASE/$f"; then
    return 0
  fi
  curl -fsSL -o "$f" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${BRANCH}/tools/yokuumakun_lan_site_publish/$f"
}

cd "$TMP"
for f in \
  patch_automation_jst_eod_guard.py \
  patch_race_day_stop_sudo_sys.py \
  ensure_race_day_stop_cron.sh \
  install_race_day_stop_timer.py \
  yokuum-race-day-stop.service.example \
  yokuum-race-day-stop.timer.example
do
  fetch "$f"
done
fetch_lan morning_bulk_publish_watch.py || true
fetch_lan clear_latest_public_snapshot.py || true
chmod +x ensure_race_day_stop_cron.sh

# ツールを server_deployment / root に恒久コピー
DEST="${ROOT}/server_deployment"
mkdir -p "$DEST"
cp -f patch_automation_jst_eod_guard.py patch_race_day_stop_sudo_sys.py \
  install_race_day_stop_timer.py ensure_race_day_stop_cron.sh \
  yokuum-race-day-stop.service.example yokuum-race-day-stop.timer.example \
  "$DEST/" 2>/dev/null || true
if [[ -f morning_bulk_publish_watch.py ]]; then
  cp -f morning_bulk_publish_watch.py "$ROOT/"
  echo "INFO: installed fixed morning_bulk_publish_watch.py (no EOD republish)"
fi
if [[ -f clear_latest_public_snapshot.py ]]; then
  cp -f clear_latest_public_snapshot.py "$ROOT/"
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

export YOKUMAKUN_SUDO_PASS="${SUDO_PASS}"
export YOKUMAKUN_ROOT="$ROOT"

persist_sudo_pass_to_env

echo "INFO: patch automation JST EOD guard"
"$PY" patch_automation_jst_eod_guard.py "$ROOT" || true

echo "INFO: patch race_day_stop (sudo_sys + .env load)"
"$PY" patch_race_day_stop_sudo_sys.py "$ROOT" || true

echo "INFO: install systemd timer (primary: daily 20:00 Asia/Tokyo)"
"$PY" install_race_day_stop_timer.py "$ROOT" || {
  echo "WARN: systemd timer install failed — cron backup still applied"
}

echo "INFO: ensure crontab backup (CRON_TZ=Asia/Tokyo)"
bash ensure_race_day_stop_cron.sh || true

# すでに 20:00 JST を過ぎていれば即停止 + latest クリア
HOUR="$(TZ=Asia/Tokyo date +%H)"
if [[ "$HOUR" -ge 20 ]]; then
  echo "WARN: already past 20:00 JST — stop automation + clear latest"
  STOP="${ROOT}/server_deployment/race_day_stop_hwm.sh"
  [[ -f "$STOP" ]] || STOP="${ROOT}/race_day_stop_hwm.sh"
  if [[ -f "$STOP" ]]; then
    bash "$STOP" || true
  else
    echo "WARN: stop script missing; falling back to systemctl stop"
    sudo_run systemctl stop yokuum-server-automation-x.service || true
  fi
  # publish-watch が埋め戻さないよう先に watch を更新済み。latest をクリア。
  if [[ -f "$ROOT/clear_latest_public_snapshot.py" ]]; then
    echo "INFO: clearing public latest.json"
    (cd "$ROOT" && "$PY" clear_latest_public_snapshot.py) || true
  fi
else
  echo "INFO: before 20:00 JST — next fire via yokuum-race-day-stop.timer / cron"
fi

echo "INFO: automation state: $(systemctl is-active yokuum-server-automation-x.service 2>/dev/null || echo unknown)"
echo "INFO: timer enabled: $(systemctl is-enabled yokuum-race-day-stop.timer 2>/dev/null || echo unknown)"
systemctl list-timers yokuum-race-day-stop.timer --no-pager 2>/dev/null || true
echo "DONE: race-day 20:00 JST auto-stop + EOD clear hardening installed"

#!/usr/bin/env bash
# サーバー上で実行: 翌日以降 05:00 に automation が確実に起動するよう恒久設定
# 例:
#   export YOKUMAKUN_SUDO_PASS='…'
#   curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-timetable-guard-19c2/tools/yokuumakun_race_day_start/bootstrap_on_server.sh | bash
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/race-day-timetable-guard-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_race_day_start"
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

# bust CDN/proxy caches so re-runs pick up installer fixes
CACHE_BUST="$(date +%s)"
fetch() {
  local f="$1"
  if curl -fsSL -o "$f" "${BASE}/${f}?t=${CACHE_BUST}"; then
    return 0
  fi
  # jsDelivr branch tip can lag; prefer commit-ish raw above
  curl -fsSL -o "$f" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${BRANCH}/tools/yokuumakun_race_day_start/${f}"
}

persist_sudo_pass_to_env() {
  [[ -n "$SUDO_PASS" ]] || return 0
  local envf="${ROOT}/.env"
  mkdir -p "$ROOT"
  touch "$envf"
  if grep -qE '^YOKUMAKUN_SUDO_PASS=' "$envf" 2>/dev/null; then
    echo "INFO: YOKUMAKUN_SUDO_PASS already present in $envf"
  else
    printf '\n# used by race_day_start/stop (cron/systemd, non-interactive sudo)\nYOKUMAKUN_SUDO_PASS=%s\n' "$SUDO_PASS" >>"$envf"
    chmod 600 "$envf" || true
    echo "INFO: appended YOKUMAKUN_SUDO_PASS to $envf"
  fi
}

echo "INFO: race-day START bootstrap root=$ROOT branch=$BRANCH"
echo "INFO: system time: $(TZ=Asia/Tokyo date -Iseconds)"
timedatectl 2>/dev/null | grep -i 'Time zone' || true

cd "$TMP"
for f in \
  race_day_start_wrapper.sh \
  race_day_start_miss_watch.py \
  ensure_race_day_start_cron.sh \
  install_race_day_start_timer.py \
  yokuum-race-day-start.service.example \
  yokuum-race-day-start.timer.example \
  yokuum-race-day-start-guard.service.example \
  yokuum-race-day-start-guard.timer.example
do
  fetch "$f"
done
chmod +x race_day_start_wrapper.sh ensure_race_day_start_cron.sh

DEST="${ROOT}/server_deployment"
mkdir -p "$DEST" "$ROOT/logs"
cp -f race_day_start_wrapper.sh race_day_start_miss_watch.py \
  ensure_race_day_start_cron.sh install_race_day_start_timer.py \
  yokuum-race-day-start.service.example yokuum-race-day-start.timer.example \
  yokuum-race-day-start-guard.service.example yokuum-race-day-start-guard.timer.example \
  "$DEST/"
chmod +x "$DEST/race_day_start_wrapper.sh" "$DEST/ensure_race_day_start_cron.sh"

persist_sudo_pass_to_env
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SUDO_PASS="$SUDO_PASS"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-$SUDO_PASS}"

PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

echo "=== install systemd timers (05:00 + 05:15) ==="
# Run from TMP so installer src != server_deployment dst (avoids shutil.SameFileError)
"$PY" "$TMP/install_race_day_start_timer.py" "$ROOT"

echo "=== install cron backup ==="
bash "$DEST/ensure_race_day_start_cron.sh"

echo "=== verify ==="
systemctl is-enabled yokuum-race-day-start.timer yokuum-race-day-start-guard.timer 2>&1 || true
systemctl list-timers 'yokuum-race-day-start*' --no-pager 2>&1 || true
crontab -l 2>/dev/null | grep -nE 'CRON_TZ|race_day_start|preflight' || true

echo "DONE: race-day start timetable armed (05:00 start + 05:15 miss-guard)"

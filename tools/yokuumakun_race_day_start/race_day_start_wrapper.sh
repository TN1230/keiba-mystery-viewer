#!/usr/bin/env bash
# Hardened wrapper around server_deployment/race_day_start_hwm.sh
# - TZ=Asia/Tokyo
# - load .env (YOKUMAKUN_SUDO_PASS for non-interactive sudo)
# - fall back to systemctl start if start script leaves unit inactive
set -uo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
SERVICE="${YOKUMAKUN_SERVER_AUTO_SERVICE:-yokuum-server-automation-x.service}"
export TZ=Asia/Tokyo
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SERVER_AUTO_SERVICE="$SERVICE"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/cron_race_day_start.log"

{
  echo "==== race_day_start_wrapper $(date -Iseconds) ===="
  echo "root=$ROOT service=$SERVICE"
} >>"$LOG"

# load .env for sudo pass / runtime
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" || true
  set +a
fi
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"

sudo_run() {
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo -n "$@" 2>/dev/null || sudo "$@"
  fi
}

START="$ROOT/server_deployment/race_day_start_hwm.sh"
if [[ ! -f "$START" ]]; then
  START="$ROOT/race_day_start_hwm.sh"
fi

if [[ -f "$START" ]]; then
  chmod +x "$START" || true
  echo "INFO: running $START" >>"$LOG"
  set +e
  bash "$START" >>"$LOG" 2>&1
  RC=$?
  set -e
  echo "INFO: start script rc=$RC" >>"$LOG"
else
  echo "WARN: race_day_start_hwm.sh missing — systemctl start only" >>"$LOG"
  RC=1
fi

ACTIVE="$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)"
echo "INFO: after start script active=$ACTIVE" >>"$LOG"
if [[ "$ACTIVE" != "active" ]]; then
  echo "WARN: forcing systemctl start $SERVICE" >>"$LOG"
  set +e
  sudo_run systemctl start "$SERVICE" >>"$LOG" 2>&1
  set -e
  sleep 2
  ACTIVE="$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)"
  echo "INFO: after systemctl start active=$ACTIVE" >>"$LOG"
fi

if [[ "$ACTIVE" == "active" ]]; then
  echo "OK: automation active" >>"$LOG"
  exit 0
fi
echo "ERROR: automation still not active" >>"$LOG"
exit 1

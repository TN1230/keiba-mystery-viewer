#!/usr/bin/env bash
# 05:00 start + 05:15 miss-guard を crontab に登録（systemd timer の保険）
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
WRAPPER="${ROOT}/server_deployment/race_day_start_wrapper.sh"
GUARD="${ROOT}/server_deployment/race_day_start_miss_watch.py"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

mkdir -p "${ROOT}/logs"
chmod +x "$WRAPPER" 2>/dev/null || true

LINE_START="0 5 * * * YOKUMAKUN_ROOT=${ROOT} YOKUMAKUN_SERVER_AUTO_SERVICE=yokuum-server-automation-x.service TZ=Asia/Tokyo ${WRAPPER} >> ${ROOT}/logs/cron_race_day_start.log 2>&1"
LINE_GUARD="15 5 * * * YOKUMAKUN_ROOT=${ROOT} YOKUMAKUN_SERVER_AUTO_SERVICE=yokuum-server-automation-x.service TZ=Asia/Tokyo ${PY} ${GUARD} >> ${ROOT}/logs/race_day_start_miss_watch.log 2>&1"
# keep existing preflight if present; do not remove other jobs
MARKER_START="race_day_start_wrapper.sh"
MARKER_GUARD="race_day_start_miss_watch.py"
# also replace legacy race_day_start_hwm.sh cron with wrapper
LEGACY="race_day_start_hwm.sh"

EXISTING="$(crontab -l 2>/dev/null || true)"
TMP="$(mktemp)"
{
  echo "CRON_TZ=Asia/Tokyo"
  printf '%s\n' "$EXISTING" \
    | grep -vE '^CRON_TZ=' \
    | grep -vF "$MARKER_START" \
    | grep -vF "$MARKER_GUARD" \
    | grep -vF "$LEGACY" \
    || true
  echo "$LINE_START"
  echo "$LINE_GUARD"
} >"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "DONE: installed start/guard cron (CRON_TZ=Asia/Tokyo)"
echo "$LINE_START"
echo "$LINE_GUARD"
crontab -l | grep -nE 'CRON_TZ|race_day_start|preflight' || true

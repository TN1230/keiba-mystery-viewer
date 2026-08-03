#!/usr/bin/env bash
# 開催日 20:00 JST の race_day_stop_hwm.sh を crontab に登録する（systemd timer の保険）
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
STOP="${ROOT}/server_deployment/race_day_stop_hwm.sh"
if [[ ! -f "$STOP" ]]; then
  STOP="${ROOT}/race_day_stop_hwm.sh"
fi
if [[ ! -f "$STOP" ]]; then
  echo "ERROR: race_day_stop_hwm.sh not found under $ROOT" >&2
  exit 1
fi
chmod +x "$STOP" || true

LOG="${ROOT}/logs/cron_race_day_stop.log"
mkdir -p "${ROOT}/logs"

MARKER="race_day_stop_hwm.sh"
LINE="0 20 * * * YOKUMAKUN_ROOT=${ROOT} YOKUMAKUN_SERVER_AUTO_SERVICE=yokuum-server-automation-x.service TZ=Asia/Tokyo ${STOP} >> ${LOG} 2>&1"

EXISTING="$(crontab -l 2>/dev/null || true)"
TMP="$(mktemp)"
{
  echo "CRON_TZ=Asia/Tokyo"
  # 既存行から本ジョブと旧 CRON_TZ を除いて残す
  printf '%s\n' "$EXISTING" | grep -v "${MARKER}" | grep -vE '^CRON_TZ=' || true
  echo "$LINE"
} >"$TMP"

crontab "$TMP"
rm -f "$TMP"

echo "DONE: installed cron (CRON_TZ=Asia/Tokyo) line:"
echo "$LINE"
echo "INFO: primary schedule is systemd yokuum-race-day-stop.timer; cron is backup"
crontab -l | grep -nE 'CRON_TZ|race_day_stop' || true

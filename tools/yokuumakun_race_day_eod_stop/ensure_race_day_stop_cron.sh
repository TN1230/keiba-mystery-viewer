#!/usr/bin/env bash
# 開催日 20:00 JST の race_day_stop_hwm.sh を crontab に登録する
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

# cron はシステムのローカル時刻で動く。Asia/Tokyo であることを確認推奨。
LINE="0 20 * * * YOKUMAKUN_ROOT=${ROOT} YOKUMAKUN_SERVER_AUTO_SERVICE=yokuum-server-automation-x.service ${STOP} >> ${LOG} 2>&1"

TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'race_day_stop_hwm\.sh' >"$TMP" || true
echo "$LINE" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "DONE: installed cron line:"
echo "$LINE"
echo "INFO: verify timezone with: timedatectl | grep -i 'Time zone'  (expect Asia/Tokyo)"
crontab -l | grep -n 'race_day_stop' || true

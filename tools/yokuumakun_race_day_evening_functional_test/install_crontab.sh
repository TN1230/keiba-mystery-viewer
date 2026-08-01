#!/usr/bin/env bash
# crontab に 21:00 ジョブを冪等登録する（CRON_TZ=Asia/Tokyo 付き）
set -euo pipefail
ROOT="${1:-${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}}"
SCRIPT="${2:-$ROOT/server_deployment/race_day_evening_functional_test.py}"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
MARKER="# yokuumakun race_day_evening_functional_test"
LINE="0 21 * * * cd ${ROOT} && TZ=Asia/Tokyo ${PY} ${SCRIPT} >> ${ROOT}/logs/race_day_evening_functional_test_cron.log 2>&1"

mkdir -p "${ROOT}/logs"
EXISTING="$(crontab -l 2>/dev/null || true)"
TMP="$(mktemp)"
{
  echo "CRON_TZ=Asia/Tokyo"
  printf '%s\n' "$EXISTING" \
    | grep -vF 'race_day_evening_functional_test' \
    | grep -vF "$MARKER" \
    | grep -vE '^CRON_TZ=' \
    || true
  echo "$MARKER"
  echo "$LINE"
} >"$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "INFO: crontab refreshed (CRON_TZ=Asia/Tokyo):"
crontab -l | grep -nE 'CRON_TZ|race_day_evening_functional_test' || true

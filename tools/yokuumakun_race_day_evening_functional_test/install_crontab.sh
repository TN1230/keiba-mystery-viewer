#!/usr/bin/env bash
# crontab に 21:00 ジョブを冪等登録する
set -euo pipefail
ROOT="${1:-${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}}"
SCRIPT="${2:-$ROOT/server_deployment/race_day_evening_functional_test.py}"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
MARKER="# yokuumakun race_day_evening_functional_test"
LINE="0 21 * * * cd ${ROOT} && ${PY} ${SCRIPT} >> ${ROOT}/logs/race_day_evening_functional_test_cron.log 2>&1"

mkdir -p "${ROOT}/logs"
EXISTING="$(crontab -l 2>/dev/null || true)"
# 旧エントリ除去
FILTERED="$(printf '%s\n' "$EXISTING" | grep -vF 'race_day_evening_functional_test' | grep -vF "$MARKER" || true)"
{
  printf '%s\n' "$FILTERED"
  echo "$MARKER"
  echo "$LINE"
} | crontab -
echo "INFO: crontab refreshed:"
crontab -l | grep -F "race_day_evening_functional_test" || true

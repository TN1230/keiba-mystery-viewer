#!/usr/bin/env bash
# 開催日タイムテーブル一括適用:
#   05:00 start + 05:15 miss-guard
#   20:00 stop + clear latest + publish-watch EOD guard
#   21:00 evening functional test (full-day checks + autofix)
#
# 例:
#   export YOKUMAKUN_SUDO_PASS='…'
#   curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-timetable-guard-19c2/tools/yokuumakun_race_day_timetable/bootstrap_on_server.sh | bash
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/race-day-timetable-guard-19c2}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SUDO_PASS="$SUDO_PASS"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-$SUDO_PASS}"

RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}"

run_remote_bootstrap() {
  local path="$1"
  echo ""
  echo "######## bootstrap $path ########"
  curl -fsSL "${RAW}/${path}" | bash -s -- "$BRANCH"
}

echo "INFO: race-day TIMETABLE bootstrap root=$ROOT branch=$BRANCH"
echo "INFO: now_jst=$(TZ=Asia/Tokyo date -Iseconds)"

run_remote_bootstrap "tools/yokuumakun_race_day_start/bootstrap_on_server.sh"
run_remote_bootstrap "tools/yokuumakun_race_day_eod_stop/bootstrap_on_server.sh"
run_remote_bootstrap "tools/yokuumakun_race_day_evening_functional_test/bootstrap_on_server.sh"

# publish watch EOD-safe script (from this branch lan pack)
echo ""
echo "######## refresh morning_bulk_publish_watch (EOD-safe) ########"
TMP="$(mktemp -d)"
curl -fsSL -o "$TMP/morning_bulk_publish_watch.py" \
  "${RAW}/tools/yokuumakun_lan_site_publish/morning_bulk_publish_watch.py" || true
curl -fsSL -o "$TMP/clear_latest_public_snapshot.py" \
  "${RAW}/tools/yokuumakun_lan_site_publish/clear_latest_public_snapshot.py" || true
if [[ -f "$TMP/morning_bulk_publish_watch.py" ]]; then
  cp -f "$TMP/morning_bulk_publish_watch.py" "$ROOT/morning_bulk_publish_watch.py"
  echo "INFO: installed $ROOT/morning_bulk_publish_watch.py"
fi
if [[ -f "$TMP/clear_latest_public_snapshot.py" ]]; then
  cp -f "$TMP/clear_latest_public_snapshot.py" "$ROOT/clear_latest_public_snapshot.py"
  echo "INFO: installed $ROOT/clear_latest_public_snapshot.py"
fi
rm -rf "$TMP"

echo ""
echo "==== timetable summary ===="
systemctl list-timers 'yokuum-race-day-*' 'yokuum-morning-publish-watch.timer' --no-pager 2>&1 || true
echo "---- crontab (race_day / CRON_TZ / evening) ----"
crontab -l 2>/dev/null | grep -nE 'CRON_TZ|race_day_|evening_functional|preflight|publish' || true

echo ""
echo "DONE: race-day timetable armed"
echo "  04:30 preflight (既存 cron があれば維持)"
echo "  05:00 start timer/cron"
echo "  05:15 start miss-guard"
echo "  05:30+ publish-watch"
echo "  20:00 stop + clear"
echo "  21:00 evening full-day test + autofix"

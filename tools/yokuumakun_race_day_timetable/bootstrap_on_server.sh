#!/usr/bin/env bash
# 開催日タイムテーブル一括適用:
#   05:00 start + 05:15 miss-guard
#   20:00 stop + clear latest + publish-watch EOD guard
#   21:00 evening functional test (full-day checks + autofix)
#
# 例（ブランチ tip の raw CDN は最大 ~5 分古いことがあるので SHA 固定推奨）:
#   export YOKUMAKUN_SUDO_PASS='…'
#   REF=cursor/race-day-timetable-guard-19c2
#   SHA=$(curl -fsSL -H 'Accept: application/vnd.github.sha' \
#     "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${REF}")
#   curl -fsSL "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}/tools/yokuumakun_race_day_timetable/bootstrap_on_server.sh" \
#     | bash -s -- "$SHA"
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
REF="${1:-cursor/race-day-timetable-guard-19c2}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SUDO_PASS="$SUDO_PASS"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-$SUDO_PASS}"

resolve_sha() {
  local ref="$1"
  # Full SHA (40 hex) or short SHA — use as-is (avoids branch-tip CDN staleness)
  if [[ "$ref" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    echo "$ref"
    return 0
  fi
  local sha
  sha="$(curl -fsSL -H 'Accept: application/vnd.github.sha' \
    "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${ref}" 2>/dev/null || true)"
  if [[ "$sha" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "$sha"
    return 0
  fi
  sha="$(curl -fsSL "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${ref}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])')"
  echo "$sha"
}

SHA="$(resolve_sha "$REF")"
RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}"
export YOKUMAKUN_BOOTSTRAP_SHA="$SHA"

run_remote_bootstrap() {
  local path="$1"
  echo ""
  echo "######## bootstrap $path (sha=${SHA:0:12}) ########"
  # Prefer commit-pinned raw (not cached as stale branch tip). Fallback: jsDelivr @sha
  if ! curl -fsSL "${RAW}/${path}" | bash -s -- "$SHA"; then
    echo "WARN: raw fetch failed for $path — trying jsDelivr"
    curl -fsSL "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${SHA}/${path}" | bash -s -- "$SHA"
  fi
}

echo "INFO: race-day TIMETABLE bootstrap root=$ROOT ref=$REF sha=${SHA:0:12}"
echo "INFO: now_jst=$(TZ=Asia/Tokyo date -Iseconds)"

run_remote_bootstrap "tools/yokuumakun_race_day_start/bootstrap_on_server.sh"
run_remote_bootstrap "tools/yokuumakun_race_day_eod_stop/bootstrap_on_server.sh"
run_remote_bootstrap "tools/yokuumakun_race_day_evening_functional_test/bootstrap_on_server.sh"

# publish watch EOD-safe script (from this commit lan pack)
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
echo "DONE: race-day timetable armed (sha=${SHA:0:12})"
echo "  04:30 preflight (既存 cron があれば維持)"
echo "  05:00 start timer/cron"
echo "  05:15 start miss-guard"
echo "  05:30+ publish-watch"
echo "  20:00 stop + clear"
echo "  21:00 evening full-day test + autofix"

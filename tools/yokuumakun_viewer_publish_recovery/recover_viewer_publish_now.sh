#!/usr/bin/env bash
# Diagnose why public viewer is not auto-published, then recover if possible.
# Run on tn1230server:
#   bash recover_viewer_publish_now.sh
set -u
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
DAY="${YOKUMAKUN_DAY:-$(TZ=Asia/Tokyo date +%Y-%m-%d)}"
YMD="$(printf '%s' "$DAY" | tr -d '-')"
SERVICE="${YOKUMAKUN_SERVER_AUTO_SERVICE:-yokuum-server-automation-x.service}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
PUBLISH_BRANCH="${YOKUMAKUN_PUBLISH_BRANCH:-main}"
PYBIN="$ROOT/.venv/bin/python"
[[ -x "$PYBIN" ]] || PYBIN="python3"

log() { printf '%s\n' "$*"; }
section() { printf '\n==== %s ====\n' "$1"; }

sudo_run() {
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo -n "$@" 2>/dev/null || sudo "$@"
  fi
}

print_latest() {
  "$PYBIN" -c '
import json, urllib.request
url="https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json"
try:
    d=json.loads(urllib.request.urlopen(url, timeout=20).read().decode())
    races=d.get("races") if isinstance(d.get("races"), dict) else {}
    print({
        "schedule_date": d.get("schedule_date"),
        "race_count": len(races) if races else int(d.get("race_count") or 0),
        "cleared": d.get("cleared"),
        "updated_at": d.get("updated_at") or d.get("published_at"),
        "venue_count": d.get("venue_count"),
    })
except Exception as e:
    print("ERR", type(e).__name__, e)
'
}

section "time / root"
log "now_jst=$(TZ=Asia/Tokyo date -Iseconds)"
log "root=$ROOT day=$DAY service=$SERVICE"

section "1) runtime"
log "automation=$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)"
log "admin=$(systemctl is-active yokuum-admin-panel.service 2>/dev/null || echo missing)"
log "publish_timer=$(systemctl is-active yokuum-morning-publish-watch.timer 2>/dev/null || echo missing)"
pgrep -af 'hwm_server_automation|morning_bulk|pre_race|force_publish|publish_watch' | head -n 40 || log "(no related procs)"

section "2) morning-bulk artifacts for $DAY"
# note: cache files on this server use YYYYMMDD (no hyphens)
for f in \
  "$ROOT/logs/morning_bulk_races_${YMD}.pkl" \
  "$ROOT/logs/morning_bulk_races_${DAY}.pkl" \
  "$ROOT/logs/morning_bulk_done_${DAY}.flag" \
  "$ROOT/logs/morning_bulk_done_${YMD}.flag"
do
  if [[ -e "$f" ]]; then ls -lah "$f"; else log "missing $f"; fi
done
ls -lt "$ROOT/logs"/morning_bulk_races_*.pkl 2>/dev/null | head -n 8 || log "(no pkl at all)"
ls -lt "$ROOT/logs"/morning_bulk_done_*.flag 2>/dev/null | head -n 8 || log "(no done flags)"

CACHE_OK=0
DONE_OK=0
[[ -f "$ROOT/logs/morning_bulk_races_${YMD}.pkl" || -f "$ROOT/logs/morning_bulk_races_${DAY}.pkl" ]] && CACHE_OK=1
[[ -f "$ROOT/logs/morning_bulk_done_${DAY}.flag" || -f "$ROOT/logs/morning_bulk_done_${YMD}.flag" ]] && DONE_OK=1
log "cache_ok=$CACHE_OK done_ok=$DONE_OK"

if [[ "$CACHE_OK" -eq 1 ]]; then
  "$PYBIN" -c "
import pickle
from pathlib import Path
for name in ('morning_bulk_races_${YMD}.pkl','morning_bulk_races_${DAY}.pkl'):
    p=Path('$ROOT')/'logs'/name
    if p.is_file():
        obj=pickle.load(p.open('rb'))
        print(f'cache_file={p.name} n={len(obj) if hasattr(obj,\"__len__\") else \"?\"}')
        break
"
fi

section "3) public latest BEFORE"
print_latest

section "4) ensure automation running"
AUTO_STATE="$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)"
if [[ "$AUTO_STATE" != "active" ]]; then
  log "WARN: automation inactive -> start"
  if [[ -x "$ROOT/server_deployment/race_day_start_hwm.sh" ]]; then
    YOKUMAKUN_ROOT="$ROOT" YOKUMAKUN_SERVER_AUTO_SERVICE="$SERVICE" \
      bash "$ROOT/server_deployment/race_day_start_hwm.sh" 2>&1 | tail -n 50 || true
  fi
  # start script may still leave it inactive without sudo; force unit start
  if [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)" != "active" ]]; then
    log "INFO: systemctl start $SERVICE"
    sudo_run systemctl start "$SERVICE" 2>&1 | tail -n 30 || true
  fi
  sleep 3
  log "automation_now=$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)"
  systemctl --no-pager -l status "$SERVICE" 2>&1 | sed -n '1,25p' || true
else
  log "OK automation already active"
fi

section "4b) cron start/preflight tails"
tail -n 40 "$ROOT/logs/cron_race_day_start.log" 2>/dev/null || log "(no start log)"
echo "----"
tail -n 40 "$ROOT/logs/cron_race_day_preflight.log" 2>/dev/null || log "(no preflight log)"

section "5) publish watch decision (if tool present)"
if [[ -f "$ROOT/morning_bulk_publish_watch.py" ]]; then
  (
    cd "$ROOT"
    "$PYBIN" -c "
import json
from pathlib import Path
import morning_bulk_publish_watch as w
root=Path('.')
day='$DAY'
snap=w._fetch_public()
dec=w.decide_publish(root, day, snap)
print(json.dumps(dec, ensure_ascii=False, default=str)[:2000])
"
  ) 2>&1 | tail -n 40 || true
else
  log "WARN: morning_bulk_publish_watch.py missing in root"
fi

section "6) force publish if today's cache exists"
PUB_RC=99
if [[ "$CACHE_OK" -eq 1 || "$DONE_OK" -eq 1 ]]; then
  cd "$ROOT"
  if [[ ! -f force_publish_public_snapshot.py ]]; then
    log "INFO: downloading force_publish_public_snapshot.py"
    curl -fsSL \
      "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${PUBLISH_BRANCH}/tools/yokuumakun_lan_site_publish/force_publish_public_snapshot.py" \
      -o force_publish_public_snapshot.py || true
    curl -fsSL \
      "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${PUBLISH_BRANCH}/tools/yokuumakun_lan_site_publish/standalone_publish_from_cache.py" \
      -o standalone_publish_from_cache.py || true
  fi
  set +e
  "$PYBIN" force_publish_public_snapshot.py
  PUB_RC=$?
  set -e
  log "force_publish rc=$PUB_RC"
else
  log "BLOCKER: no morning-bulk cache/done for $DAY — cannot publish races yet"
  log "ACTION: automation を起動したうえで朝一斉を走らせる / 管理画面『① 一斉予想再実行』"
  section "recent automation debug"
  tail -n 50 "$ROOT/logs/server_automation_debug.jsonl" 2>/dev/null || log "(no automation debug)"
fi

section "7) kick publish-watch oneshot"
sudo_run systemctl start yokuum-morning-publish-watch.service 2>&1 | tail -n 20 || true
journalctl -u yokuum-morning-publish-watch.service -n 30 --no-pager 2>&1 | tail -n 30 || true

section "8) public latest AFTER"
sleep 2
print_latest

section "summary"
log "cache_ok=$CACHE_OK done_ok=$DONE_OK force_publish_rc=$PUB_RC"
log "automation=$(systemctl is-active "$SERVICE" 2>/dev/null || echo missing)"
if [[ "$CACHE_OK" -eq 0 && "$DONE_OK" -eq 0 ]]; then
  log "verdict=NO_TODAY_CACHE — 朝一斉が未完了。公開以前に予想キャッシュが無い"
  log "next=1) sudo systemctl start $SERVICE"
  log "next=2) 管理画面で『① 一斉予想再実行』または朝スロット完了を待つ"
  log "next=3) 完了後に本スクリプト再実行 / force_publish"
elif [[ "$PUB_RC" -eq 0 ]]; then
  log "verdict=PUBLISH_ATTEMPTED_OK — latest の race_count を確認"
else
  log "verdict=PUBLISH_FAILED_OR_SKIPPED — 上記 force_publish エラーを確認"
fi
log "DONE"

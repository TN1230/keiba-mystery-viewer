#!/usr/bin/env bash
# Probe yokuumakun_auto-x runtime / standby state on the LAN server.
set -u
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
DAY="${YOKUMAKUN_DAY:-$(TZ=Asia/Tokyo date +%Y-%m-%d)}"
NOW_JST="$(TZ=Asia/Tokyo date '+%Y-%m-%d %H:%M:%S %Z')"

section() { printf '\n==== %s ====\n' "$1"; }

section "host / time"
hostname 2>/dev/null || true
echo "now_jst=$NOW_JST"
echo "root=$ROOT"
echo "day=$DAY"
uptime 2>/dev/null || true
df -h / /opt /home 2>/dev/null | sed -n '1,8p' || true

section "systemd (automation / admin / timers)"
for u in \
  yokuum-server-automation-x.service \
  yokuum-admin-panel.service \
  yokuum-morning-publish-watch.service \
  yokuum-morning-publish-watch.timer \
  yokuum-race-day-stop.service \
  yokuum-race-day-stop.timer \
  cloudflared.service \
  yokuum-ssh-tcp-tunnel.service
do
  active="$(systemctl is-active "$u" 2>/dev/null || echo missing)"
  enabled="$(systemctl is-enabled "$u" 2>/dev/null || echo n/a)"
  printf '%-42s active=%-10s enabled=%s\n' "$u" "$active" "$enabled"
done
echo
systemctl list-units --type=service --all 'yokuum*' 2>/dev/null | sed -n '1,40p' || true
echo
systemctl list-timers --all 'yokuum*' 2>/dev/null | sed -n '1,40p' || true

section "systemd status (automation head)"
systemctl --no-pager -l status yokuum-server-automation-x.service 2>/dev/null | sed -n '1,28p' || echo "(no automation unit)"

section "processes"
pgrep -af 'hwm_server_automation|morning_bulk|pre_race|admin_panel|cloudflared|streamlit|hwm\.py|publish_watch|race_day' 2>/dev/null | head -n 80 || echo "(none)"

section "worker pids / locks / standby markers"
ls -lah "$ROOT/logs/worker_pids" 2>/dev/null | sed -n '1,40p' || echo "(no worker_pids)"
ls -lah "$ROOT/logs"/*lock* "$ROOT/logs"/*standby* "$ROOT/logs"/*pending* 2>/dev/null | sed -n '1,40p' || echo "(no lock/standby/pending markers)"

section "today morning-bulk / cache"
ls -lah "$ROOT/logs"/morning_bulk*"$DAY"* 2>/dev/null | sed -n '1,40p' || echo "(no morning_bulk files for $DAY)"
if [[ -f "$ROOT/logs/morning_bulk_races_${DAY}.pkl" ]]; then
  python3 - <<PY 2>/dev/null || true
import pickle
from pathlib import Path
p=Path("$ROOT/logs/morning_bulk_races_${DAY}.pkl")
obj=pickle.load(p.open("rb"))
n=len(obj) if hasattr(obj,"__len__") else "?"
print(f"cache_pickle={p} type={type(obj).__name__} n={n}")
PY
fi

section "recent automation debug (last 20)"
if [[ -f "$ROOT/logs/server_automation_debug.jsonl" ]]; then
  tail -n 20 "$ROOT/logs/server_automation_debug.jsonl"
else
  echo "(no server_automation_debug.jsonl)"
fi

section "recent admin ops (last 15)"
if [[ -f "$ROOT/logs/admin_ops.jsonl" ]]; then
  tail -n 15 "$ROOT/logs/admin_ops.jsonl"
else
  echo "(no admin_ops.jsonl)"
fi

section "cron (tn + hints)"
crontab -l 2>/dev/null | grep -Ei 'yokuu|race_day|morning|publish|backup|週|friday' || echo "(no matching user cron)"
ls /etc/cron.d 2>/dev/null | head -n 30 || true

section "public snapshot quick check (if network)"
python3 - <<'PY' 2>/dev/null || echo "(skip public check)"
import json, urllib.request
from datetime import datetime, timezone, timedelta
JST=timezone(timedelta(hours=9))
base="https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer"
for path in ["admin_api.json","snapshots/latest.json"]:
    try:
        with urllib.request.urlopen(base+"/"+path, timeout=15) as r:
            d=json.loads(r.read().decode())
        if path.endswith("admin_api.json"):
            print("admin_api", d)
        else:
            races=d.get("races") if isinstance(d.get("races"), dict) else {}
            print("latest", {
                "schedule_date": d.get("schedule_date") or d.get("day"),
                "race_count": len(races),
                "cleared": d.get("cleared"),
                "finalized": d.get("finalized"),
                "updated_at": d.get("updated_at") or d.get("published_at"),
                "venue_count": d.get("venue_count"),
            })
    except Exception as e:
        print(path, "ERR", e)
print("now_jst", datetime.now(JST).isoformat(timespec="seconds"))
PY

section "summary heuristics"
AUTO="$(systemctl is-active yokuum-server-automation-x.service 2>/dev/null || echo missing)"
ADMIN="$(systemctl is-active yokuum-admin-panel.service 2>/dev/null || echo missing)"
HWM_N="$(pgrep -af 'hwm_server_automation.py' 2>/dev/null | wc -l | tr -d ' ')"
MB_N="$(pgrep -af 'morning_bulk' 2>/dev/null | wc -l | tr -d ' ')"
PR_N="$(pgrep -af 'pre_race' 2>/dev/null | wc -l | tr -d ' ')"
echo "automation_unit=$AUTO"
echo "admin_unit=$ADMIN"
echo "hwm_automation_procs=$HWM_N"
echo "morning_bulk_procs=$MB_N"
echo "pre_race_procs=$PR_N"
HOUR="$(TZ=Asia/Tokyo date +%H)"
DOW="$(TZ=Asia/Tokyo date +%u)"  # 1=Mon ... 6=Sat 7=Sun
if [[ "$AUTO" == "active" && "$HWM_N" -ge 1 ]]; then
  echo "verdict_runtime=RUNNING (automation active)"
elif [[ "$AUTO" == "inactive" || "$AUTO" == "failed" ]]; then
  echo "verdict_runtime=STOPPED (automation not active)"
else
  echo "verdict_runtime=UNKNOWN ($AUTO)"
fi
if [[ "$DOW" -ge 6 && "$HOUR" -ge 20 ]]; then
  echo "verdict_standby=Likely EOD/off-hours for race-day (Sat/Sun after 20:00 JST) — waiting for next race day / weekly jobs is normal"
elif [[ "$DOW" -ge 6 && "$HOUR" -lt 6 ]]; then
  echo "verdict_standby=Pre-morning window — expect standby until morning bulk slots"
else
  echo "verdict_standby=Check timers/cron above for next expected wake"
fi
echo
echo "DONE"

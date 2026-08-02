#!/usr/bin/env bash
# paramiko / SFTP で /tmp に置いたパックを、GitHub curl なしで適用する。
# deploy_paramiko.py から呼ばれる想定。
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BASE="${1:-/tmp/race_day_timetable_deploy}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"

is_placeholder_pass() {
  case "${1:-}" in
    ''|'…'|'...'|'....'|'YOUR_PASSWORD'|'your_password'|'changeme'|'password') return 0 ;;
  esac
  [[ "${1:-}" == *'←'* ]] && return 0
  return 1
}

if is_placeholder_pass "$SUDO_PASS"; then
  if [[ -f "$ROOT/.env" ]]; then
    line="$(grep -E '^YOKUMAKUN_SUDO_PASS=' "$ROOT/.env" 2>/dev/null | tail -n1 || true)"
    val="${line#YOKUMAKUN_SUDO_PASS=}"
    val="${val%$'\r'}"
    val="${val#\"}"; val="${val%\"}"
    val="${val#\'}"; val="${val%\'}"
    SUDO_PASS="$val"
  fi
fi
if is_placeholder_pass "$SUDO_PASS"; then
  echo "ERROR: usable YOKUMAKUN_SUDO_PASS missing (docs placeholder?)" >&2
  exit 2
fi

if ! printf '%s\n' "$SUDO_PASS" | sudo -S -p '' -v 2>/dev/null; then
  echo "ERROR: sudo authentication failed for $(id -un)" >&2
  exit 2
fi

# persist working password
python3 - "$ROOT/.env" "$SUDO_PASS" <<'PY'
import pathlib, sys
root_env = pathlib.Path(sys.argv[1])
pw = sys.argv[2]
root_env.parent.mkdir(parents=True, exist_ok=True)
text = root_env.read_text(encoding="utf-8", errors="replace") if root_env.is_file() else ""
lines = text.splitlines()
out, done = [], False
for line in lines:
    if line.startswith("YOKUMAKUN_SUDO_PASS=") and not done:
        out.append("YOKUMAKUN_SUDO_PASS=" + pw)
        done = True
    else:
        out.append(line)
if not done:
    if out and out[-1].strip():
        out.append("")
    out.append("# used by race_day_start/stop (cron/systemd, non-interactive sudo)")
    out.append("YOKUMAKUN_SUDO_PASS=" + pw)
root_env.write_text("\n".join(out) + "\n", encoding="utf-8")
root_env.chmod(0o600)
print("INFO: wrote YOKUMAKUN_SUDO_PASS to", root_env)
PY

export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SUDO_PASS="$SUDO_PASS"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-$SUDO_PASS}"

PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"
DEST="${ROOT}/server_deployment"
mkdir -p "$DEST" "$ROOT/logs"

echo "INFO: apply_uploaded_packs root=$ROOT base=$BASE"
echo "INFO: sudo auth ok for $(id -un)"
echo "INFO: now_jst=$(TZ=Asia/Tokyo date -Iseconds)"

# ---- start ----
START="$BASE/start"
echo ""
echo "######## start pack ########"
cp -f \
  "$START/race_day_start_wrapper.sh" \
  "$START/race_day_start_miss_watch.py" \
  "$START/ensure_race_day_start_cron.sh" \
  "$START/install_race_day_start_timer.py" \
  "$START/yokuum-race-day-start.service.example" \
  "$START/yokuum-race-day-start.timer.example" \
  "$START/yokuum-race-day-start-guard.service.example" \
  "$START/yokuum-race-day-start-guard.timer.example" \
  "$DEST/"
chmod +x "$DEST/race_day_start_wrapper.sh" "$DEST/ensure_race_day_start_cron.sh"
set +e
"$PY" "$START/install_race_day_start_timer.py" "$ROOT"
START_RC=$?
set -e
bash "$DEST/ensure_race_day_start_cron.sh"
echo "INFO: start timer_rc=$START_RC"

# ---- eod stop ----
EOD="$BASE/eod"
echo ""
echo "######## eod stop pack ########"
cp -f \
  "$EOD/patch_automation_jst_eod_guard.py" \
  "$EOD/patch_race_day_stop_sudo_sys.py" \
  "$EOD/ensure_race_day_stop_cron.sh" \
  "$EOD/install_race_day_stop_timer.py" \
  "$EOD/yokuum-race-day-stop.service.example" \
  "$EOD/yokuum-race-day-stop.timer.example" \
  "$DEST/" 2>/dev/null || true
chmod +x "$DEST/ensure_race_day_stop_cron.sh" 2>/dev/null || true
"$PY" "$EOD/patch_automation_jst_eod_guard.py" "$ROOT" || true
"$PY" "$EOD/patch_race_day_stop_sudo_sys.py" "$ROOT" || true
set +e
"$PY" "$EOD/install_race_day_stop_timer.py" "$ROOT"
EOD_RC=$?
set -e
bash "$EOD/ensure_race_day_stop_cron.sh" || true
echo "INFO: eod timer_rc=$EOD_RC"

# ---- evening ----
EVE="$BASE/evening"
echo ""
echo "######## evening functional test ########"
cp -f "$EVE/race_day_evening_functional_test.py" "$DEST/race_day_evening_functional_test.py"
chmod +x "$DEST/race_day_evening_functional_test.py"
if [[ -f "$EVE/install_crontab.sh" ]]; then
  cp -f "$EVE/install_crontab.sh" "$DEST/install_evening_crontab.sh"
  chmod +x "$DEST/install_evening_crontab.sh"
fi
"$PY" -m py_compile "$DEST/race_day_evening_functional_test.py"
if [[ -f "$EVE/install_crontab.sh" ]]; then
  bash "$EVE/install_crontab.sh" "$ROOT" "$DEST/race_day_evening_functional_test.py"
else
  MARKER="# yokuumakun race_day_evening_functional_test"
  LINE="0 21 * * * cd $ROOT && $PY $DEST/race_day_evening_functional_test.py >> $ROOT/logs/race_day_evening_functional_test_cron.log 2>&1"
  EXISTING="$(crontab -l 2>/dev/null || true)"
  if ! echo "$EXISTING" | grep -Fq "race_day_evening_functional_test.py"; then
    {
      echo "$EXISTING"
      echo "$MARKER"
      echo "$LINE"
    } | crontab -
  fi
fi

# ---- publish watch (EOD-safe) ----
PUB="$BASE/publish"
echo ""
echo "######## publish watch (EOD-safe) ########"
if [[ -f "$PUB/morning_bulk_publish_watch.py" ]]; then
  cp -f "$PUB/morning_bulk_publish_watch.py" "$ROOT/morning_bulk_publish_watch.py"
  echo "INFO: installed $ROOT/morning_bulk_publish_watch.py"
fi
if [[ -f "$PUB/clear_latest_public_snapshot.py" ]]; then
  cp -f "$PUB/clear_latest_public_snapshot.py" "$ROOT/clear_latest_public_snapshot.py"
  echo "INFO: installed $ROOT/clear_latest_public_snapshot.py"
fi

echo ""
echo "==== timetable summary ===="
systemctl list-timers 'yokuum-race-day-*' 'yokuum-morning-publish-watch.timer' --no-pager 2>&1 || true
echo "---- crontab (race_day / CRON_TZ / evening) ----"
crontab -l 2>/dev/null | grep -nE 'CRON_TZ|race_day_|evening_functional|preflight|publish' || true

if [[ "$START_RC" -ne 0 || "$EOD_RC" -ne 0 ]]; then
  echo "WARN: one or more systemd timer installs failed (cron backup should still be armed)" >&2
  echo "DONE: race-day timetable applied with warnings"
  exit 1
fi
echo "DONE: race-day timetable armed via LAN upload"
exit 0

#!/usr/bin/env bash
# サーバー上で実行: 翌日以降 05:00 に automation が確実に起動するよう恒久設定
# 例:
#   export YOKUMAKUN_SUDO_PASS='…'
#   bash bootstrap_on_server.sh <commit-sha-or-branch>
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
REF="${1:-${YOKUMAKUN_BOOTSTRAP_SHA:-cursor/race-day-timetable-guard-19c2}}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

is_placeholder_pass() {
  case "${1:-}" in
    ''|'…'|'...'|'....'|'YOUR_PASSWORD'|'your_password'|'changeme'|'password') return 0 ;;
  esac
  [[ "${1:-}" == *'←'* ]] && return 0
  return 1
}

resolve_sudo_pass() {
  local from_export="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
  local from_file="" line val
  if [[ -f "$ROOT/.env" ]]; then
    line="$(grep -E '^YOKUMAKUN_SUDO_PASS=' "$ROOT/.env" 2>/dev/null | tail -n1 || true)"
    val="${line#YOKUMAKUN_SUDO_PASS=}"
    val="${val%$'\r'}"
    val="${val#\"}"; val="${val%\"}"
    val="${val#\'}"; val="${val%\'}"
    from_file="$val"
  fi
  is_placeholder_pass "$from_export" && from_export=""
  is_placeholder_pass "$from_file" && from_file=""
  SUDO_PASS="${from_export:-$from_file}"
}

resolve_sha() {
  local ref="$1"
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
  curl -fsSL "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${ref}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])'
}

resolve_sudo_pass
SHA="$(resolve_sha "$REF")"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}/tools/yokuumakun_race_day_start"
JSDELIVR="https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${SHA}/tools/yokuumakun_race_day_start"

sudo_run() {
  if [[ -n "${SUDO_PASS:-}" ]]; then
    printf '%s\n' "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo -n "$@" 2>/dev/null || sudo "$@"
  fi
}

fetch() {
  local f="$1"
  if curl -fsSL -o "$f" "${BASE}/${f}"; then
    return 0
  fi
  curl -fsSL -o "$f" "${JSDELIVR}/${f}"
}

persist_sudo_pass_to_env() {
  [[ -n "$SUDO_PASS" ]] || return 0
  local envf="${ROOT}/.env"
  mkdir -p "$ROOT"
  touch "$envf"
  if grep -qE '^YOKUMAKUN_SUDO_PASS=' "$envf" 2>/dev/null; then
    echo "INFO: YOKUMAKUN_SUDO_PASS already present in $envf"
  else
    printf '\n# used by race_day_start/stop (cron/systemd, non-interactive sudo)\nYOKUMAKUN_SUDO_PASS=%s\n' "$SUDO_PASS" >>"$envf"
    chmod 600 "$envf" || true
    echo "INFO: appended YOKUMAKUN_SUDO_PASS to $envf"
  fi
}

echo "INFO: race-day START bootstrap root=$ROOT ref=$REF sha=${SHA:0:12}"
echo "INFO: system time: $(TZ=Asia/Tokyo date -Iseconds)"
timedatectl 2>/dev/null | grep -i 'Time zone' || true

cd "$TMP"
for f in \
  race_day_start_wrapper.sh \
  race_day_start_miss_watch.py \
  ensure_race_day_start_cron.sh \
  install_race_day_start_timer.py \
  yokuum-race-day-start.service.example \
  yokuum-race-day-start.timer.example \
  yokuum-race-day-start-guard.service.example \
  yokuum-race-day-start-guard.timer.example
do
  fetch "$f"
done
chmod +x race_day_start_wrapper.sh ensure_race_day_start_cron.sh

# Prove we are not about to run a stale SameFile-vulnerable installer from DEST
if ! grep -q 'SameFileError' install_race_day_start_timer.py; then
  echo "ERROR: fetched install_race_day_start_timer.py looks stale (no SameFileError guard)" >&2
  echo "ERROR: sha=${SHA} — refuse to continue" >&2
  exit 1
fi

DEST="${ROOT}/server_deployment"
mkdir -p "$DEST" "$ROOT/logs"
cp -f race_day_start_wrapper.sh race_day_start_miss_watch.py \
  ensure_race_day_start_cron.sh install_race_day_start_timer.py \
  yokuum-race-day-start.service.example yokuum-race-day-start.timer.example \
  yokuum-race-day-start-guard.service.example yokuum-race-day-start-guard.timer.example \
  "$DEST/"
chmod +x "$DEST/race_day_start_wrapper.sh" "$DEST/ensure_race_day_start_cron.sh"

persist_sudo_pass_to_env
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SUDO_PASS="${SUDO_PASS:-}"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-${SUDO_PASS:-}}"

PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY="$(command -v python3)"

echo "=== install systemd timers (05:00 + 05:15) ==="
# Run from TMP so installer src != server_deployment dst (avoids shutil.SameFileError)
echo "INFO: running installer from $TMP/install_race_day_start_timer.py"
set +e
"$PY" "$TMP/install_race_day_start_timer.py" "$ROOT"
TIMER_RC=$?
set -e
if [[ "$TIMER_RC" -ne 0 ]]; then
  echo "WARN: systemd timer install failed (rc=$TIMER_RC) — cron backup still applied" >&2
  echo "WARN: usually bad YOKUMAKUN_SUDO_PASS (docs '…' placeholder or wrong password)" >&2
fi

echo "=== install cron backup ==="
bash "$DEST/ensure_race_day_start_cron.sh"

echo "=== verify ==="
systemctl is-enabled yokuum-race-day-start.timer yokuum-race-day-start-guard.timer 2>&1 || true
systemctl list-timers 'yokuum-race-day-start*' --no-pager 2>&1 || true
crontab -l 2>/dev/null | grep -nE 'CRON_TZ|race_day_start|preflight' || true

echo "DONE: race-day start timetable armed (05:00 start + 05:15 miss-guard) sha=${SHA:0:12}"

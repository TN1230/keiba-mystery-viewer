#!/usr/bin/env bash
# 開催日タイムテーブル一括適用:
#   05:00 start + 05:15 miss-guard
#   20:00 stop + clear latest + publish-watch EOD guard
#   21:00 evening functional test (full-day checks + autofix)
#
# 例（ブランチ tip の raw CDN は古いことがあるので SHA 固定推奨）:
#   export YOKUMAKUN_SUDO_PASS='ここに本物のsudoパスワード'
#   REF=cursor/race-day-timetable-guard-19c2
#   SHA=$(curl -fsSL "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${REF}" \
#     | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])')
#   curl -fsSL "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}/tools/yokuumakun_race_day_timetable/bootstrap_on_server.sh" \
#     | bash -s -- "$SHA"
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
REF="${1:-cursor/race-day-timetable-guard-19c2}"

is_placeholder_pass() {
  case "${1:-}" in
    ''|'…'|'...'|'....'|'YOUR_PASSWORD'|'your_password'|'changeme'|'password') return 0 ;;
  esac
  # docs placeholder containing fullwidth dots / arrow hints
  [[ "$1" == *'←'* ]] && return 0
  return 1
}

read_env_sudo_pass() {
  local envf="${ROOT}/.env" line val
  [[ -f "$envf" ]] || return 0
  line="$(grep -E '^YOKUMAKUN_SUDO_PASS=' "$envf" 2>/dev/null | tail -n1 || true)"
  [[ -n "$line" ]] || return 0
  val="${line#YOKUMAKUN_SUDO_PASS=}"
  val="${val%$'\r'}"
  val="${val#\"}"; val="${val%\"}"
  val="${val#\'}"; val="${val%\'}"
  printf '%s' "$val"
}

write_env_sudo_pass() {
  local pw="$1" envf="${ROOT}/.env" tmp
  mkdir -p "$ROOT"
  touch "$envf"
  chmod 600 "$envf" || true
  tmp="$(mktemp)"
  # python avoids shell-metachar breakage in password values
  python3 - "$envf" "$pw" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
pw = sys.argv[2]
text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
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
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print("updated" if done else "appended")
PY
  chmod 600 "$envf" || true
  rm -f "$tmp"
  echo "INFO: wrote YOKUMAKUN_SUDO_PASS to $envf"
}

resolve_sudo_pass() {
  local from_export="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
  local from_file
  from_file="$(read_env_sudo_pass || true)"
  if is_placeholder_pass "$from_export"; then
    from_export=""
  fi
  if is_placeholder_pass "$from_file"; then
    from_file=""
  fi
  SUDO_PASS="${from_export:-$from_file}"
}

sudo_ok() {
  [[ -n "${SUDO_PASS:-}" ]] || return 1
  # passwd_tries=1 avoids "try again" consuming empty stdin
  printf '%s\n' "$SUDO_PASS" | sudo -S -p '' -v 2>/dev/null
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
  sha="$(curl -fsSL "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${ref}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])')"
  echo "$sha"
}

resolve_sudo_pass
if ! sudo_ok; then
  echo "ERROR: sudo authentication failed (or YOKUMAKUN_SUDO_PASS unset/placeholder)." >&2
  echo "ERROR: systemd timer install needs a real sudo password for user $(id -un)." >&2
  echo "ERROR: Fix with ONE of:" >&2
  echo "  export YOKUMAKUN_SUDO_PASS='実際のsudoパスワード'" >&2
  echo "  # or edit ${ROOT}/.env  → YOKUMAKUN_SUDO_PASS=実際のsudoパスワード" >&2
  echo "ERROR: Tip: if .env still has '…' from docs, replace it with the real password." >&2
  exit 1
fi
# persist working password (fixes prior placeholder in .env)
write_env_sudo_pass "$SUDO_PASS"
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_SUDO_PASS="$SUDO_PASS"
export YOKUMAKUN_SSH_PASS="${YOKUMAKUN_SSH_PASS:-$SUDO_PASS}"

SHA="$(resolve_sha "$REF")"
RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}"
export YOKUMAKUN_BOOTSTRAP_SHA="$SHA"
BOOT_TMP="$(mktemp -d)"
cleanup() { rm -rf "$BOOT_TMP"; }
trap cleanup EXIT

run_remote_bootstrap() {
  local path="$1"
  local local_sh="${BOOT_TMP}/$(basename "$path").$$.sh"
  echo ""
  echo "######## bootstrap $path (sha=${SHA:0:12}) ########"
  if ! curl -fsSL -o "$local_sh" "${RAW}/${path}"; then
    echo "WARN: raw fetch failed for $path — trying jsDelivr"
    curl -fsSL -o "$local_sh" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${SHA}/${path}"
  fi
  bash "$local_sh" "$SHA"
}

echo "INFO: race-day TIMETABLE bootstrap root=$ROOT ref=$REF sha=${SHA:0:12}"
echo "INFO: sudo auth ok for $(id -un)"
echo "INFO: now_jst=$(TZ=Asia/Tokyo date -Iseconds)"

run_remote_bootstrap "tools/yokuumakun_race_day_start/bootstrap_on_server.sh"
run_remote_bootstrap "tools/yokuumakun_race_day_eod_stop/bootstrap_on_server.sh"
run_remote_bootstrap "tools/yokuumakun_race_day_evening_functional_test/bootstrap_on_server.sh"

# publish watch EOD-safe script (from this commit lan pack)
echo ""
echo "######## refresh morning_bulk_publish_watch (EOD-safe) ########"
curl -fsSL -o "$BOOT_TMP/morning_bulk_publish_watch.py" \
  "${RAW}/tools/yokuumakun_lan_site_publish/morning_bulk_publish_watch.py" || true
curl -fsSL -o "$BOOT_TMP/clear_latest_public_snapshot.py" \
  "${RAW}/tools/yokuumakun_lan_site_publish/clear_latest_public_snapshot.py" || true
if [[ -f "$BOOT_TMP/morning_bulk_publish_watch.py" ]]; then
  cp -f "$BOOT_TMP/morning_bulk_publish_watch.py" "$ROOT/morning_bulk_publish_watch.py"
  echo "INFO: installed $ROOT/morning_bulk_publish_watch.py"
fi
if [[ -f "$BOOT_TMP/clear_latest_public_snapshot.py" ]]; then
  cp -f "$BOOT_TMP/clear_latest_public_snapshot.py" "$ROOT/clear_latest_public_snapshot.py"
  echo "INFO: installed $ROOT/clear_latest_public_snapshot.py"
fi

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

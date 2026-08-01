#!/usr/bin/env bash
# サーバー上で実行: 開催日 21:00 機能テストランナーを配置し crontab 登録する
# 例:
#   bash bootstrap_on_server.sh
#   bash bootstrap_on_server.sh cursor/race-day-timetable-guard-19c2
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
REF="${1:-${YOKUMAKUN_BOOTSTRAP_SHA:-cursor/race-day-timetable-guard-19c2}}"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

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

SHA="$(resolve_sha "$REF")"
BRANCH="$SHA"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}/tools/yokuumakun_race_day_evening_functional_test"

sudo_run() {
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo "$@"
  fi
}

fetch() {
  local f="$1"
  if curl -fsSL -o "$f" "$BASE/$f"; then
    return 0
  fi
  curl -fsSL -o "$f" "https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@${SHA}/tools/yokuumakun_race_day_evening_functional_test/$f"
}

echo "INFO: race-day evening functional test bootstrap root=$ROOT ref=$REF sha=${SHA:0:12}"

cd "$TMP"
fetch race_day_evening_functional_test.py
fetch install_crontab.sh || true

DEST_DIR="$ROOT/server_deployment"
if [[ ! -d "$DEST_DIR" ]]; then
  DEST_DIR="$ROOT"
fi
mkdir -p "$DEST_DIR" "$ROOT/logs"

cp -f race_day_evening_functional_test.py "$DEST_DIR/race_day_evening_functional_test.py"
chmod +x "$DEST_DIR/race_day_evening_functional_test.py"
echo "INFO: installed $DEST_DIR/race_day_evening_functional_test.py"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
"$PY" -m py_compile "$DEST_DIR/race_day_evening_functional_test.py"
echo "INFO: py_compile ok"

# crontab 登録
if [[ -f install_crontab.sh ]]; then
  bash install_crontab.sh "$ROOT" "$DEST_DIR/race_day_evening_functional_test.py"
else
  MARKER="# yokuumakun race_day_evening_functional_test"
  LINE="0 21 * * * cd $ROOT && $PY $DEST_DIR/race_day_evening_functional_test.py >> $ROOT/logs/race_day_evening_functional_test_cron.log 2>&1"
  EXISTING="$(crontab -l 2>/dev/null || true)"
  if echo "$EXISTING" | grep -Fq "race_day_evening_functional_test.py"; then
    echo "INFO: crontab entry already present"
  else
    {
      echo "$EXISTING"
      echo "$MARKER"
      echo "$LINE"
    } | crontab -
    echo "INFO: crontab installed: $LINE"
  fi
fi

# .env に Webhook キーの存在を確認（値は触らない）
ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  if grep -Eq '^(DISCORD_WEBHOOK_TEST|ADMIN_TEST_WEBHOOK_URL|HWM_DISCORD_WEBHOOK_TEST|DISCORD_TEST_WEBHOOK_URL)=' "$ENV_FILE"; then
    echo "INFO: test webhook env key found in .env"
  else
    echo "WARN: set DISCORD_WEBHOOK_TEST in $ENV_FILE (test channel)"
  fi
else
  echo "WARN: $ENV_FILE missing — webhook may fall back to ops_discord_notify"
fi

# 短いドライラン（開催日でなければスキップ通知）
export YOKUMAKUN_ROOT="$ROOT"
export YOKUMAKUN_EOD_TEST_BUDGET_SEC="${YOKUMAKUN_EOD_TEST_BUDGET_SEC:-120}"
echo "INFO: dry-run (budget=${YOKUMAKUN_EOD_TEST_BUDGET_SEC}s)"
set +e
"$PY" "$DEST_DIR/race_day_evening_functional_test.py" --budget-sec="$YOKUMAKUN_EOD_TEST_BUDGET_SEC"
RC=$?
set -e
echo "INFO: dry-run rc=$RC"

echo "DONE: race_day_evening_functional_test installed (cron 21:00 JST assumed)"
crontab -l 2>/dev/null | grep -F "race_day_evening_functional_test" || true

#!/usr/bin/env bash
# bore.pub で SSH(22) をインターネット側 TCP として公開し、到達情報を Supabase に載せる。
# Cloudflare Quick Tunnel は HTTP 専用のため、クラウドエージェント向けには bore を使う。
set -euo pipefail

export TZ=Asia/Tokyo
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/ssh_tcp_tunnel.log"
ENDPOINT_FILE="${LOG_DIR}/ssh_endpoint.local.json"
BIN_DIR="${ROOT}/.local/bin"
BORE_BIN="${BORE_BIN:-${BIN_DIR}/bore}"
BORE_TO="${BORE_TO:-bore.pub}"
BORE_VERSION="${BORE_VERSION:-0.5.2}"
PUBLISH_PY="${ROOT}/publish_ssh_endpoint.py"
PY="${ROOT}/.venv/bin/python3"
SSH_USER="${SSH_TUNNEL_USER:-tn}"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

install_bore() {
  if [[ -x "$BORE_BIN" ]]; then
    return 0
  fi
  mkdir -p "$BIN_DIR"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) target="x86_64-unknown-linux-musl" ;;
    aarch64|arm64) target="aarch64-unknown-linux-musl" ;;
    *)
      log "ERROR: unsupported arch: $arch"
      exit 1
      ;;
  esac
  url="https://github.com/ekzhang/bore/releases/download/v${BORE_VERSION}/bore-v${BORE_VERSION}-${target}.tar.gz"
  tmp="$(mktemp -d)"
  log "INFO: downloading bore from $url"
  curl -fsSL "$url" -o "$tmp/bore.tgz"
  tar -xzf "$tmp/bore.tgz" -C "$tmp"
  install -m 0755 "$tmp/bore" "$BORE_BIN"
  rm -rf "$tmp"
  log "INFO: installed $BORE_BIN"
}

notify_discord() {
  local host="$1" port="$2"
  local webhook="" webhook_line=""
  if [[ -f "${ROOT}/.env" ]]; then
    webhook_line="$(grep -E '^(DISCORD_WEBHOOK_TEST_ALWAYS|DISCORD_WEBHOOK_OPS)=' "${ROOT}/.env" | head -1 || true)"
    if [[ -n "$webhook_line" ]]; then
      webhook="${webhook_line#*=}"
      webhook="$(printf '%s' "$webhook" | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
    fi
  fi
  if [[ -z "$webhook" ]]; then
    return 0
  fi
  local content payload
  content="SSH tunnel up: ssh -p ${port} ${SSH_USER}@${host} (bore)"
  payload="$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1]}))' "$content")"
  curl -fsS -X POST -H 'Content-Type: application/json' -d "$payload" \
    "$webhook" >/dev/null 2>&1 || log "WARN: discord notify failed"
}

write_local_endpoint() {
  local host="$1" port="$2"
  cat >"$ENDPOINT_FILE" <<EOF
{
  "host": "${host}",
  "port": ${port},
  "user": "${SSH_USER}",
  "provider": "bore",
  "ssh_command": "ssh -p ${port} ${SSH_USER}@${host}",
  "updated_at": "$(date -Iseconds)"
}
EOF
  log "LOCAL_ENDPOINT $ENDPOINT_FILE"
  # 画面/journal にも必ず出す（curl|bash の確認用）
  echo "SSH_ENDPOINT_READY host=${host} port=${port} user=${SSH_USER}"
  echo "SSH_COMMAND: ssh -p ${port} ${SSH_USER}@${host}"
}

publish_endpoint() {
  local host="$1" port="$2"
  write_local_endpoint "$host" "$port"
  notify_discord "$host" "$port"
  if [[ ! -f "$PUBLISH_PY" ]]; then
    log "WARN: missing $PUBLISH_PY (skip supabase publish)"
    return 0
  fi
  if [[ ! -x "$PY" ]]; then
    PY="$(command -v python3 || true)"
  fi
  if [[ -z "${PY:-}" ]]; then
    log "WARN: python3 not found (skip supabase publish)"
    return 0
  fi
  set +e
  out="$("$PY" "$PUBLISH_PY" --host "$host" --port "$port" --user "$SSH_USER" --provider bore --note "ssh tcp via bore" 2>&1)"
  rc=$?
  set -e
  log "publish rc=$rc $out"
}

extract_endpoint() {
  # bore / 派生の表記ゆれを吸収
  local line="$1"
  if [[ "$line" =~ [Ll]istening[[:space:]]+(at|on)[[:space:]]+([A-Za-z0-9._-]+):([0-9]{2,5}) ]]; then
    echo "${BASH_REMATCH[2]} ${BASH_REMATCH[3]}"
    return 0
  fi
  if [[ "$line" =~ ([A-Za-z0-9._-]*bore[A-Za-z0-9._-]*):([0-9]{2,5}) ]]; then
    echo "${BASH_REMATCH[1]} ${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

install_bore
log "START ssh_tcp_tunnel bore=$BORE_BIN to=$BORE_TO local=127.0.0.1:22"

# pipe サブシェルを避け、FIFO で読む（publish を確実に親で実行）
fifo="$(mktemp -u)"
mkfifo "$fifo"
bore_pid=""
cleanup_fifo() {
  if [[ -n "${bore_pid:-}" ]] && kill -0 "$bore_pid" 2>/dev/null; then
    kill "$bore_pid" 2>/dev/null || true
  fi
  rm -f "$fifo"
}
trap cleanup_fifo EXIT

if command -v stdbuf >/dev/null 2>&1; then
  stdbuf -oL -eL "$BORE_BIN" local 22 --to "$BORE_TO" >"$fifo" 2>&1 &
else
  "$BORE_BIN" local 22 --to "$BORE_TO" >"$fifo" 2>&1 &
fi
bore_pid=$!

published=0
while IFS= read -r line; do
  echo "$line" | tee -a "$LOG_FILE" >/dev/null
  echo "$line"
  if ep="$(extract_endpoint "$line")"; then
    host="${ep%% *}"
    port="${ep##* }"
    log "ENDPOINT host=$host port=$port"
    publish_endpoint "$host" "$port"
    published=1
  fi
done <"$fifo"

wait "$bore_pid" || true
log "STOP ssh_tcp_tunnel (bore exited) published=$published"
exit 1

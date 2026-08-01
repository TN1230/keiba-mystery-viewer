#!/usr/bin/env bash
# bore.pub で SSH(22) をインターネット側 TCP として公開し、到達情報を Supabase に載せる。
# Cloudflare Quick Tunnel は HTTP 専用のため、クラウドエージェント向けには bore を使う。
set -euo pipefail

export TZ=Asia/Tokyo
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/ssh_tcp_tunnel.log"
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

publish_endpoint() {
  local host="$1" port="$2"
  if [[ ! -f "$PUBLISH_PY" ]]; then
    log "WARN: missing $PUBLISH_PY (skip publish)"
    return 0
  fi
  if [[ ! -x "$PY" ]]; then
    PY="$(command -v python3 || true)"
  fi
  if [[ -z "${PY:-}" ]]; then
    log "WARN: python3 not found (skip publish)"
    return 0
  fi
  set +e
  out="$("$PY" "$PUBLISH_PY" --host "$host" --port "$port" --user "$SSH_USER" --provider bore --note "ssh tcp via bore" 2>&1)"
  rc=$?
  set -e
  log "publish rc=$rc $out"
}

install_bore
log "START ssh_tcp_tunnel bore=$BORE_BIN to=$BORE_TO local=127.0.0.1:22"

run_bore() {
  if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$BORE_BIN" local 22 --to "$BORE_TO"
  else
    "$BORE_BIN" local 22 --to "$BORE_TO"
  fi
}

# bore は "listening at bore.pub:PORT" を出す
published=0
run_bore 2>&1 | tee -a "$LOG_FILE" | while IFS= read -r line; do
  if [[ "$line" =~ [Ll]istening\ at\ ([A-Za-z0-9._-]+):([0-9]{2,5}) ]]; then
    host="${BASH_REMATCH[1]}"
    port="${BASH_REMATCH[2]}"
    log "ENDPOINT host=$host port=$port"
    publish_endpoint "$host" "$port"
    published=1
  fi
done

log "STOP ssh_tcp_tunnel (bore exited)"
exit 1

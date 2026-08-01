#!/usr/bin/env bash
# サーバー上で実行: SSH を bore.pub 経由でインターネット側へ出し、到達情報を公開する
# 例:
#   curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_ssh_internet_tunnel/bootstrap_on_server.sh | bash
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/ssh-internet-tunnel-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_ssh_internet_tunnel"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

cd "$TMP"
for f in ssh_tcp_tunnel.sh publish_ssh_endpoint.py yokuum-ssh-tcp-tunnel.service.example; do
  curl -fsSL -o "$f" "$BASE/$f"
done

mkdir -p "$ROOT/server_deployment" "$ROOT/logs" "$ROOT/.local/bin"
# CRLF 除去
sed -i 's/\r$//' ssh_tcp_tunnel.sh
install -m 0755 ssh_tcp_tunnel.sh "$ROOT/server_deployment/ssh_tcp_tunnel.sh"
install -m 0644 publish_ssh_endpoint.py "$ROOT/publish_ssh_endpoint.py"
install -m 0644 yokuum-ssh-tcp-tunnel.service.example "$ROOT/server_deployment/yokuum-ssh-tcp-tunnel.service.example"

# sshd が localhost でも受けられること（通常は ListenAddress 未指定でOK）
if ! ss -ltn | grep -qE '[:.]22\s'; then
  echo "ERROR: sshd is not listening on port 22" >&2
  exit 1
fi

UNIT_SRC="$ROOT/server_deployment/yokuum-ssh-tcp-tunnel.service.example"
UNIT_DST="/etc/systemd/system/yokuum-ssh-tcp-tunnel.service"
sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable yokuum-ssh-tcp-tunnel.service
sudo systemctl restart yokuum-ssh-tcp-tunnel.service

echo "waiting for bore endpoint publish..."
for i in $(seq 1 30); do
  if curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json" >/tmp/ssh_endpoint.json 2>/dev/null; then
    echo "ssh_endpoint.json:"
    cat /tmp/ssh_endpoint.json
    echo
    # ログにも endpoint があればOK
    if grep -q '"port"' /tmp/ssh_endpoint.json; then
      systemctl --no-pager --full status yokuum-ssh-tcp-tunnel.service | head -20 || true
      echo "DONE: SSH is published via bore. Connect with the ssh_command in ssh_endpoint.json"
      exit 0
    fi
  fi
  sleep 2
done

echo "WARN: service started but ssh_endpoint.json not updated yet; check logs:"
sudo journalctl -u yokuum-ssh-tcp-tunnel.service -n 80 --no-pager || true
tail -n 80 "$ROOT/logs/ssh_tcp_tunnel.log" || true
exit 1

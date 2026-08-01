#!/usr/bin/env bash
# サーバー上で実行: SSH を bore.pub 経由でインターネット側へ出し、到達情報を公開する
# 例:
#   curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-bore-endpoint-a29c/tools/yokuumakun_ssh_internet_tunnel/bootstrap_on_server.sh | bash
set -euo pipefail

ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${YOKUMAKUN_TUNNEL_BRANCH:-cursor/ssh-bore-endpoint-a29c}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_ssh_internet_tunnel"
SUDO_PASS="${YOKUMAKUN_SUDO_PASS:-${YOKUMAKUN_SSH_PASS:-}}"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

sudo_run() {
  # 以前成功していた方式に合わせ、パスワード付きなら sudo -S
  if [[ -n "$SUDO_PASS" ]]; then
    echo "$SUDO_PASS" | sudo -S -p '' "$@"
  else
    sudo "$@"
  fi
}

echo "INFO: bootstrap SSH internet tunnel branch=$BRANCH root=$ROOT"

if [[ ! -d "$ROOT" ]]; then
  echo "ERROR: app root not found: $ROOT" >&2
  exit 2
fi

if [[ -z "$SUDO_PASS" ]] && ! sudo -n true 2>/dev/null; then
  echo "INFO: sudo password may be required (set YOKUMAKUN_SUDO_PASS to avoid prompt)"
fi

cd "$TMP"
for f in ssh_tcp_tunnel.sh publish_ssh_endpoint.py yokuum-ssh-tcp-tunnel.service.example; do
  echo "INFO: download $f"
  curl -fsSL -o "$f" "$BASE/$f"
done

mkdir -p "$ROOT/server_deployment" "$ROOT/logs" "$ROOT/.local/bin"
# CRLF 除去
sed -i 's/\r$//' ssh_tcp_tunnel.sh
install -m 0755 ssh_tcp_tunnel.sh "$ROOT/server_deployment/ssh_tcp_tunnel.sh"
install -m 0644 publish_ssh_endpoint.py "$ROOT/publish_ssh_endpoint.py"
install -m 0644 yokuum-ssh-tcp-tunnel.service.example "$ROOT/server_deployment/yokuum-ssh-tcp-tunnel.service.example"
# tn 所有にしてサービスユーザーが書けるように
if id tn >/dev/null 2>&1; then
  chown -R tn:tn "$ROOT/server_deployment/ssh_tcp_tunnel.sh" "$ROOT/publish_ssh_endpoint.py" "$ROOT/logs" "$ROOT/.local" 2>/dev/null || \
    sudo_run chown -R tn:tn "$ROOT/server_deployment/ssh_tcp_tunnel.sh" "$ROOT/publish_ssh_endpoint.py" "$ROOT/logs" "$ROOT/.local" || true
fi

# sshd が localhost でも受けられること（通常は ListenAddress 未指定でOK）
if ! ss -ltn | grep -qE '[:.]22\s'; then
  echo "ERROR: sshd is not listening on port 22" >&2
  ss -ltn || true
  exit 1
fi
echo "INFO: sshd is listening on port 22"

UNIT_SRC="$ROOT/server_deployment/yokuum-ssh-tcp-tunnel.service.example"
UNIT_DST="/etc/systemd/system/yokuum-ssh-tcp-tunnel.service"
sudo_run cp "$UNIT_SRC" "$UNIT_DST"
sudo_run systemctl daemon-reload
sudo_run systemctl enable yokuum-ssh-tcp-tunnel.service
sudo_run systemctl restart yokuum-ssh-tcp-tunnel.service
sleep 1
if ! systemctl is-active --quiet yokuum-ssh-tcp-tunnel.service; then
  echo "ERROR: yokuum-ssh-tcp-tunnel.service failed to start" >&2
  sudo_run systemctl --no-pager --full status yokuum-ssh-tcp-tunnel.service || true
  sudo_run journalctl -u yokuum-ssh-tcp-tunnel.service -n 80 --no-pager || true
  exit 1
fi
echo "INFO: service active"

echo "waiting for bore endpoint publish..."
PUBLIC_URL="https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json"
for i in $(seq 1 45); do
  if [[ -f "$ROOT/logs/ssh_endpoint.local.json" ]]; then
    echo "local endpoint:"
    cat "$ROOT/logs/ssh_endpoint.local.json"
    echo
  fi
  if curl -fsSL "$PUBLIC_URL" >/tmp/ssh_endpoint.json 2>/dev/null; then
    echo "ssh_endpoint.json:"
    cat /tmp/ssh_endpoint.json
    echo
    if grep -q '"port"' /tmp/ssh_endpoint.json; then
      systemctl --no-pager --full status yokuum-ssh-tcp-tunnel.service | head -20 || true
      echo "DONE: SSH is published via bore. Connect with the ssh_command in ssh_endpoint.json"
      exit 0
    fi
  fi
  # journal に ENDPOINT が出ていればローカル成功（supabase だけ失敗の可能性）
  if sudo_run journalctl -u yokuum-ssh-tcp-tunnel.service -n 40 --no-pager 2>/dev/null | grep -q 'SSH_ENDPOINT_READY'; then
    echo "WARN: tunnel endpoint seen in journal but public ssh_endpoint.json not ready yet (publish may have failed)"
    sudo_run journalctl -u yokuum-ssh-tcp-tunnel.service -n 40 --no-pager | grep -E 'SSH_ENDPOINT_READY|SSH_COMMAND|publish rc=' || true
    if [[ -f "$ROOT/logs/ssh_endpoint.local.json" ]]; then
      echo "Paste this JSON to the cloud agent if Supabase publish keeps failing:"
      cat "$ROOT/logs/ssh_endpoint.local.json"
    fi
  fi
  sleep 2
done

echo "WARN: service started but ssh_endpoint.json not updated yet; check logs:"
sudo_run systemctl --no-pager --full status yokuum-ssh-tcp-tunnel.service || true
sudo_run journalctl -u yokuum-ssh-tcp-tunnel.service -n 120 --no-pager || true
tail -n 120 "$ROOT/logs/ssh_tcp_tunnel.log" || true
if [[ -f "$ROOT/logs/ssh_endpoint.local.json" ]]; then
  echo "LOCAL endpoint file exists — paste to cloud agent:"
  cat "$ROOT/logs/ssh_endpoint.local.json"
fi
exit 1

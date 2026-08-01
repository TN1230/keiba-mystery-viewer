# SSH をインターネット側へ出す（クラウドエージェント到達用）

## なぜ必要か
- 自宅LANの `192.168.128.178` はクラウドVMから届かない（別ネットワークの私有IP）
- 自宅の IPv6 はインターネット上に出ていても、**Cursor クラウドVMに IPv6 出口がない**
- 管理API用 Cloudflare Quick Tunnel は **HTTP 専用**で SSH には使えない

そのため、SSH を **IPv4 の公衆 TCP 中継（bore.pub）** で出し、到達先を Supabase の `ssh_endpoint.json` に掲載します。

## サーバーで有効化（推奨）

自宅サーバー、または LAN 内端末から:

```bash
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-internet-tunnel-19c2/tools/yokuumakun_ssh_internet_tunnel/bootstrap_on_server.sh | bash
```

Windows (LAN):

```powershell
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

公開後の到達情報:

https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json

## クラウド側からの接続例

```bash
export YOKUMAKUN_SSH_PASS='（ローカルサーバーIP.txt の pass）'
python3 tools/yokuumakun_ssh_internet_tunnel/connect_from_agent.py -- hostname
```

## セキュリティ注意
- パスワードSSHがインターネットから叩かれるようになります。可能なら鍵認証へ移行し、`PasswordAuthentication no` を検討してください
- bore のポートは再接続で変わることがあります（`ssh_endpoint.json` を都度参照）
- 不要になったら: `sudo systemctl disable --now yokuum-ssh-tcp-tunnel.service`

## ローカルサーバーIP.txt 追記例（手動）

```
# インターネット経由SSH（bore、ssh_endpoint.json を参照）
# https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/ssh_endpoint.json
```

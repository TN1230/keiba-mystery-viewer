# LAN 一括適用（未適用パッチ）

クラウドVMからは自宅 `192.168.128.178` に SSH できません（AWS 内部IPに解決される）。  
**以前成功していた方式**は Windows LAN からの `paramiko` + `echo pass | sudo -S` です。

## 推奨（Windows / LAN）

```powershell
cd <このディレクトリを clone / ダウンロードした場所>
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

資格情報: `C:\Users\mocco\Desktop\ローカルサーバーIP.txt` の `pass:`（または `YOKUMAKUN_SSH_PASS`）。

## サーバー上で直接

tunnel だけ（最短）:

```bash
export YOKUMAKUN_SUDO_PASS='83670824'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-bore-endpoint-a29c/tools/yokuumakun_lan_apply_pending/bootstrap_tunnel_embedded.sh | bash | tee /tmp/ssh_tunnel_only.log
```

一括（tunnel を先に実行。途中失敗でも続行）:

```bash
export YOKUMAKUN_SUDO_PASS='83670824'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/ssh-bore-endpoint-a29c/tools/yokuumakun_lan_apply_pending/bootstrap_on_server.sh | bash | tee /tmp/lan_apply.log
```

失敗時は必ず貼る:
```bash
tail -n 120 /tmp/lan_apply.log
systemctl status yokuum-ssh-tcp-tunnel --no-pager
journalctl -u yokuum-ssh-tcp-tunnel -n 80 --no-pager
cat /opt/yokuumakun_auto-x/logs/ssh_endpoint.local.json
```

## 適用後の確認（クラウド側）

- `ssh_endpoint.json` に `host`/`port` がある
- `snapshots/latest.json` の `schedule_date` が当日、`race_count` > 0

# yokuumakun_auto-x サーバー内バックアップ

`/opt/yokuumakun_auto-x` の現時点スナップショットを、**毎週バックアップと同じ保存先**へ作成します。

## サーバー上で実行（いま SSH している場合はこちら）

`tn@tn1230server` の bash に貼り付けてください（PowerShell / `C:\...` は不要です）。

```bash
cd /tmp
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/server-auto-x-backup-19c2/tools/yokuumakun_server_backup/backup_auto_x_on_server.sh -o backup_auto_x_on_server.sh
chmod +x backup_auto_x_on_server.sh
export YOKUMAKUN_ROOT=/opt/yokuumakun_auto-x
# /opt 配下にディレクトリ作成が必要なときだけ:
# export YOKUMAKUN_SUDO_PASS='（sudo パスワード）'
bash ./backup_auto_x_on_server.sh
```

成功すると `OK output=...` と保存先一覧が出ます。

## Windows LAN から実行

```powershell
cd C:\Users\tn\Desktop\keiba-mystery-viewer\tools\yokuumakun_server_backup
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

パスワードは `Desktop\ローカルサーバーIP.txt` の `pass:`、または環境変数 `YOKUMAKUN_SSH_PASS`。

## 保存先の決め方

サーバー上で次の順に自動検出します。

1. `YOKUMAKUN_BACKUP_DEST`（明示指定時）
2. cron / systemd のバックアップ系ジョブが指すパス
3. 既存の週次保存先（実機確認済み: `/home/tn/yokuumakun_auto-x_backups`）など
4. `/opt` 直下に `yokuumakun_auto-x_*` の兄弟コピーがある場合は `/opt`
5. 見つからない場合は `/home/tn/yokuumakun_auto-x_backups` を作成

成果物名の例:

- `yokuumakun_auto-x_manual_now_YYYYMMDD_HHMMSS.tar.gz`
- 同名の `.manifest.txt`

既定では `.venv` / `__pycache__` / `.git` を除外します（`.env` や CSV・コードは含めます）。venv も入れる場合は `export YOKUMAKUN_BACKUP_INCLUDE_VENV=1`。

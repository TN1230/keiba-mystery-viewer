# yokuumakun_auto-x サーバー内バックアップ

`/opt/yokuumakun_auto-x` の現時点スナップショットを、**毎週バックアップと同じ保存先**へ作成します。

## Windows LAN から実行（推奨）

```powershell
cd C:\Users\tn\Desktop\keiba-mystery-viewer\tools\yokuumakun_server_backup
# リポジトリ未取得なら main を pull してから:
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

パスワードは `Desktop\ローカルサーバーIP.txt` の `pass:`、または環境変数 `YOKUMAKUN_SSH_PASS`。

## 保存先の決め方

サーバー上で次の順に自動検出します。

1. `YOKUMAKUN_BACKUP_DEST`（明示指定時）
2. cron / systemd のバックアップ系ジョブが指すパス
3. `/opt/yokuumakun_backups` など、既存の `yokuumakun_auto*` バックアップがある場所
4. `/opt` 直下に `yokuumakun_auto-x_*` の兄弟コピーがある場合は `/opt`
5. 見つからない場合は `/opt/yokuumakun_backups` を作成

成果物名の例:

- `yokuumakun_auto-x_manual_now_YYYYMMDD_HHMMSS.tar.gz`
- 同名の `.manifest.txt`

既定では `.venv` / `__pycache__` / `.git` を除外します（`.env` や CSV・コードは含めます）。venv も入れる場合:

```powershell
$env:YOKUMAKUN_BACKUP_INCLUDE_VENV = "1"
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

## サーバー直実行

```bash
export YOKUMAKUN_SUDO_PASS='…'   # /opt 配下作成が必要なとき
bash tools/yokuumakun_server_backup/backup_auto_x_on_server.sh
```

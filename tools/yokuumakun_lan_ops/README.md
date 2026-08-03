# LAN 運用（Cloud Agent 不使用）

日常運用に Cloud Agent は使いません。

| 役割 | 担当 |
|---|---|
| 毎日の start / publish / stop / 21:00 検査 | **サーバの systemd timer + cron** |
| スケジュール欠けの自動修復 | **21:00 機能テストの autofix**（サーバ内ファイルを再適用） |
| コードやユニットの更新 | **自宅 Windows（同一 LAN）から paramiko 一発** |

Cloud Agent は GitHub 上のコード変更には使えますが、サーバ操作の経路には入れません。

## 初回（または更新時）— Windows だけで完了

1. このリポジトリを自宅 Windows に clone / pull
2. PowerShell:

```powershell
cd tools\yokuumakun_lan_ops
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

パスワードは `YOKUMAKUN_SSH_PASS` か Desktop の `ローカルサーバーIP.txt`（`pass:`）。

成功時: `_deploy_lan_ops_out.txt` に `RESULT: SUCCESS`。

## 状態確認だけ（任意）

```powershell
cd tools\yokuumakun_lan_ops
powershell -ExecutionPolicy Bypass -File status_from_windows.ps1
```

## その後

何もしなくてよいです。開催日は:

- 05:00 起動 → 05:15 ミス監視 → 公開監視 → 20:00 停止 → 21:00 検査＋修復

サーバ上のコマンド貼り付けや Cloud Agent への依頼は不要です。

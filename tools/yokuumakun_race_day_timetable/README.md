# 開催日タイムテーブル一括武装

翌日以降、想定どおりに自動処理が走るよう **start / stop / 21:00 テスト** をまとめて入れます。

## タイムテーブル（JST）

| 時刻 | 内容 |
|---|---|
| 04:30 | preflight（既存 cron があれば維持） |
| **05:00** | automation 起動（systemd timer + cron 保険） |
| **05:15** | 起動ミス監視（inactive なら再起動＋失敗 webhook） |
| 05:30〜 | publish-watch |
| 朝〜昼 | 朝一斉 / 直前予想 / 自動公開 |
| **20:00** | stop + latest clear |
| **21:00** | 全日チェック＋安全な自動修正＋Discord 報告 |

## 運用方針（Cloud Agent 不使用）

日常運用に Cloud Agent やサーバへの手貼りコマンドは使いません。  
入口は **`tools/yokuumakun_lan_ops`** です。

```powershell
cd tools\yokuumakun_lan_ops
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

詳細: [`../yokuumakun_lan_ops/README.md`](../yokuumakun_lan_ops/README.md)

このディレクトリの `deploy_paramiko.py` は lan_ops から呼ばれる実装本体です。

## 確認

```bash
systemctl list-timers 'yokuum-race-day-*' 'yokuum-morning-publish-watch.timer' --no-pager
crontab -l | grep -E 'CRON_TZ|race_day_|evening_functional'
```

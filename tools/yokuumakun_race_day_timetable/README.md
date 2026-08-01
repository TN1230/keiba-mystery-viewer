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

## 推奨: Windows LAN（paramiko）

クラウド Agent からは `192.168.128.178` の SSH が届かないことが多いです。  
**自宅 Windows（同一 LAN）** から、以前と同じ方式で適用します。

```powershell
cd tools\yokuumakun_race_day_timetable
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

パスワードは次のいずれか:

1. 環境変数 `YOKUMAKUN_SSH_PASS` / `YOKUU_SSH_PASS`
2. Desktop の `ローカルサーバーIP.txt` 内 `pass: …`

成功時は `_deploy_race_day_timetable_out.txt` に `RESULT: SUCCESS` と timer/cron 一覧が出ます。  
SFTP でパックを上げてサーバー上で適用するため、GitHub raw の CDN キャッシュ問題は起きません。

## 代替: サーバー直実行

```bash
export YOKUMAKUN_SUDO_PASS='実際のsudoパスワード'
REF=cursor/race-day-timetable-guard-19c2
SHA=$(curl -fsSL "https://api.github.com/repos/t-orz/keiba-mystery-viewer/commits/${REF}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["sha"])')
curl -fsSL "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${SHA}/tools/yokuumakun_race_day_timetable/bootstrap_on_server.sh" \
  | bash -s -- "$SHA"
```

## 確認

```bash
systemctl list-timers 'yokuum-race-day-*' 'yokuum-morning-publish-watch.timer' --no-pager
crontab -l | grep -E 'CRON_TZ|race_day_|evening_functional'
```

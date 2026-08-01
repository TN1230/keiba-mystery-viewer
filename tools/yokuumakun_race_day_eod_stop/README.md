# 開催日 20:00 JST 自動停止（恒久）

次回以降、**毎日 20:00（Asia/Tokyo）** に `race_day_stop_hwm.sh` が自動実行されるようにします。

## 仕組み（二重化）

| 優先 | 手段 | 時刻 |
|---|---|---|
| 本線 | systemd `yokuum-race-day-stop.timer` | `OnCalendar=*-*-* 20:00:00 Asia/Tokyo` |
| 保険 | crontab（`CRON_TZ=Asia/Tokyo`） | `0 20 * * *` |
| 最終保険 | `hwm_server_automation._tick` の JST 20:00 `SystemExit` | プロセス側 |

`hwm.py` 自体に 20:00 終了判定はありません。停止は上記の外部スケジュールが担当します。

## サーバーへの一回適用（これで次回以降ずっと有効）

```bash
export YOKUMAKUN_SUDO_PASS='…'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-eod-jst-stop-guard-19c2/tools/yokuumakun_race_day_eod_stop/bootstrap_on_server.sh | bash
```

bootstrap が行うこと:

1. automation に JST 20:00 自己停止ガードを注入
2. `race_day_stop_hwm.sh` を非対話 sudo + `.env` 読み込み対応にパッチ
3. **systemd timer を enable --now**（本線）
4. crontab に `CRON_TZ=Asia/Tokyo` + 20:00 行を登録（保険）
5. `.env` に `YOKUMAKUN_SUDO_PASS` が無ければ追記（次回以降のため）
6. すでに 20:00 JST 過ぎなら即 stop 実行

## 確認

```bash
systemctl is-enabled yokuum-race-day-stop.timer    # enabled
systemctl list-timers yokuum-race-day-stop.timer --no-pager
crontab -l | grep -E 'CRON_TZ|race_day_stop'
timedatectl | grep -i 'Time zone'
```

## 単体テスト

```bash
cd tools/yokuumakun_race_day_eod_stop
python3 -m unittest test_eod_stop_tools.py -v
```

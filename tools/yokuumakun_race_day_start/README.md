# 開催日 05:00 起動の恒久化

これまで `race_day_start` は cron 依存で、sudo / TZ / 未実行時の再試行がなく、翌朝 automation が止まったままになることがありました（例: 2026-08-02）。

## 何をするか

1. **systemd timer** `yokuum-race-day-start.timer` … 毎日 **05:00 Asia/Tokyo**
2. **miss-guard timer** `yokuum-race-day-start-guard.timer` … 毎日 **05:15**（inactive なら起動＋失敗 webhook）
3. **cron 保険**（`CRON_TZ=Asia/Tokyo`）
4. **hardened wrapper**（`.env` の sudo パス・`systemctl start` フォールバック）

## 適用

```bash
export YOKUMAKUN_SUDO_PASS='…'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-timetable-guard-19c2/tools/yokuumakun_race_day_start/bootstrap_on_server.sh | bash
```

一括（start + EOD stop + 21:00 テスト）は:

```bash
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-timetable-guard-19c2/tools/yokuumakun_race_day_timetable/bootstrap_on_server.sh | bash
```

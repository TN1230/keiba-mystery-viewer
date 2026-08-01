# 開催日 20:00 JST 終了の硬化（EOD stop）

## 結論（よくある誤解）

**`hwm.py` / `hwm_server_automation.py` は「JST を見て 20:00 に自己終了」しません。**  
20:00 の停止は **外部 cron → `race_day_stop_hwm.sh`** が担当します。

したがって「20時を過ぎても終わらない」主因は、だいたい次のいずれかです。

1. **`0 20 * * * race_day_stop_hwm.sh` が crontab に無い / 動いていない**
2. **cron から `sudo systemctl stop` が失敗**（非対話 sudo / `-x` 未許可）
3. （副次）自動化側が naive `datetime.now()` を使っていても、**20:00 終了判定自体が無い**ので「JST未認識」だけでは説明できない

`race_day_stop_hwm.sh` 自体は `export TZ=Asia/Tokyo` しています。  
cron の発火時刻は **OS のローカルタイムゾーン**依存なので、`timedatectl` で `Asia/Tokyo` であることを確認してください。

## いま公開側で見える兆候

`latest.json` が 20:00 過ぎても `cleared` でなく `race_count>0` のままなら、finalize/stop が未完了の可能性が高いです。

## このツールが入れるもの

| 項目 | 内容 |
|---|---|
| JST EOD ガード | `hwm_server_automation._tick` が **JST 20:00 以降**なら `SystemExit`（cron 失敗時の保険） |
| stop の sudo 修正 | `race_day_stop_hwm.sh` の bare `sudo` を `sudo_sys`（`YOKUMAKUN_SUDO_PASS` / `sudo -n`）へ |
| cron 登録 | 毎日 `0 20 * * *` で `race_day_stop_hwm.sh` |

## サーバー適用（推奨）

```bash
export YOKUMAKUN_SUDO_PASS='…'   # cron/stop 用
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-eod-jst-stop-guard-19c2/tools/yokuumakun_race_day_eod_stop/bootstrap_on_server.sh | bash
```

すでに 20:00 JST を過ぎている場合、bootstrap は **その場で stop を実行**します。

### 手動で今すぐ止める

```bash
export YOKUMAKUN_ROOT=/opt/yokuumakun_auto-x
export YOKUMAKUN_SUDO_PASS='…'
bash /opt/yokuumakun_auto-x/server_deployment/race_day_stop_hwm.sh
# または
sudo systemctl stop yokuum-server-automation-x.service
```

### 確認

```bash
timedatectl | grep -i 'Time zone'          # Asia/Tokyo
crontab -l | grep race_day_stop
systemctl is-active yokuum-server-automation-x.service   # inactive が正常（20時以降）
ls -lt /opt/yokuumakun_auto-x/logs/race_day_stop_*.log | head
```

## 単体テスト

```bash
cd tools/yokuumakun_race_day_eod_stop
python3 -m unittest test_eod_stop_tools.py -v
```

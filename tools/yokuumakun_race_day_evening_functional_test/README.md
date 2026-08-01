# 開催日 21:00 機能動作テスト → テスト Webhook 報告

開催日の **21:00（JST）** に、当日運用の機能が問題なく動いたかを読み取りベースで検査し、
**不具合発生点** または **不具合無し** をテスト用 Discord Webhook に通知します。

不具合検知時は、**安全な運用修復のみ** を自動実行し、対象チェックを再検査します（【自己修正】として報告）。

- 全体ハードデッドライン: **2時間以内**（`YOKUMAKUN_EOD_TEST_BUDGET_SEC` / `--budget-sec=`）
- 開催日以外: スキップ通知のみ（`--force` で強制実行）
- `race_day_stop_hwm.sh`（通常 20:00）には埋め込まない。**別 cron / timer** で 21:00 起動
- 自己修正: 既定 ON（`YOKUMAKUN_EOD_TEST_AUTOFIX=0` または `--no-autofix` で無効）

## 検査項目（概要）

| チェック | 内容 | 自己修正 |
|---|---|---|
| morning_bulk_cache | 朝一斉 cache / done flag | 対象外（過去データ） |
| race_day_stop_finalize_logs | 本日の stop/finalize ログ | 既存 stop/finalize スクリプトがあれば実行 |
| automation_stopped | 21時時点で automation が停止 | `systemctl stop` |
| no_stuck_workers | 予想ワーカー残留なし | 対象ワーカーのみ `pkill` |
| admin_health | `127.0.0.1:8791/health` | admin-panel 再起動 |
| publish_patches | pre_race / morning_bulk 公開パッチ + watch | patch スクリプト再適用 |
| publish_watch_timer | publish-watch.timer enabled | install / enable timer |
| eod_snapshot_state | 当日アーカイブ or latest クリア | finalize 手段があれば実行 |
| daytime_publish_evidence | 当日中の公開更新痕跡 | 対象外（過去証拠） |
| pdf_holmes_sample | 公開 PDF のホームズ指数（あれば） | 対象外 |
| netkeiba_light | netkeiba 到達の軽い確認 | 対象外（外部） |

破壊的操作（再予想・Selenium一斉）は行いません。自己修正も運用停止・再起動・パッチ再適用・既存 EOD スクリプト実行に限定します。

## 通知先

**テスト webhook**（常に結果を送る）優先順:

1. `DISCORD_WEBHOOK_TEST`
2. `ADMIN_TEST_WEBHOOK_URL`
3. `HWM_DISCORD_WEBHOOK_TEST`
4. `DISCORD_TEST_WEBHOOK_URL`
5. `DISCORD_WEBHOOK_TEST_ALWAYS` / `HWM_DISCORD_WEBHOOK_TEST_ALWAYS`

**エラー通知 webhook**（不具合あり / タイムアウト時のみ追加送信）:

1. `DISCORD_WEBHOOK_FAILURE`
2. `HWM_DISCORD_WEBHOOK_FAILURE`
3. `DISCORD_WEBHOOK_ERROR` / `HWM_DISCORD_WEBHOOK_ERROR`
4. `DISCORD_ERROR_WEBHOOK_URL` / `ADMIN_ERROR_WEBHOOK_URL`
5. `DISCORD_WEBHOOK_URL_3`（サーバー .env の failure チャンネル）

テスト webhook と同一 URL の場合は二重送信しません。  
未設定時は `ops_discord_notify.notify_action` にフォールバックします。

報告には【チェック一覧】に加え、修復を試みた場合は【自己修正】（FIXED / FAILED / SKIP）を含めます。自己修正で解消した場合のタイトルは「不具合無し（自己修正済）」です。

**自己修正できなかった項目**（対象外・失敗・手段なし・残存 WARN/NG）には【対処法】を付け、**テスト webhook とエラー通知 webhook の両方**に同じ本文で送ります。

## サーバーへの導入

### A. bootstrap（推奨）

サーバー上で:

```bash
cd /tmp
curl -fsSL -o bootstrap_on_server.sh \
  "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-evening-autofix-19c2/tools/yokuumakun_race_day_evening_functional_test/bootstrap_on_server.sh"
bash bootstrap_on_server.sh
```

またはブランチ指定:

```bash
bash bootstrap_on_server.sh cursor/race-day-evening-autofix-19c2
```

これで以下を行います:

1. ランナーを `/opt/yokuumakun_auto-x/server_deployment/`（なければルート）へ配置
2. crontab に `0 21 * * *`（JST想定のシステム時刻）を登録
3. 疎通として `--budget-sec=120` のドライラン（開催日判定付き）

### B. 手動

```bash
ROOT=/opt/yokuumakun_auto-x
curl -fsSL -o "$ROOT/server_deployment/race_day_evening_functional_test.py" \
  "https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/race-day-evening-autofix-19c2/tools/yokuumakun_race_day_evening_functional_test/race_day_evening_functional_test.py"

# crontab（既存に追記）
( crontab -l 2>/dev/null; cat <<'EOF'
# 開催日 21:00 機能動作テスト → テストWebhook（不具合時は安全な自己修正あり）
0 21 * * * cd /opt/yokuumakun_auto-x && /opt/yokuumakun_auto-x/.venv/bin/python /opt/yokuumakun_auto-x/server_deployment/race_day_evening_functional_test.py >> /opt/yokuumakun_auto-x/logs/race_day_evening_functional_test_cron.log 2>&1
EOF
) | crontab -
```

`.env` にテスト Webhook があることを確認:

```env
DISCORD_WEBHOOK_TEST=https://discord.com/api/webhooks/...
# 任意: sudo が必要な修復用（systemctl stop/restart 等）
# YOKUMAKUN_SUDO_PASS=...
# 自己修正を切る場合:
# YOKUMAKUN_EOD_TEST_AUTOFIX=0
```

## 手動実行

```bash
cd /opt/yokuumakun_auto-x
# 通常（非開催日はスキップ通知）
.venv/bin/python server_deployment/race_day_evening_functional_test.py

# 強制（非開催日でも検査）
.venv/bin/python server_deployment/race_day_evening_functional_test.py --force --budget-sec=300

# 自己修正なしで検査のみ
.venv/bin/python server_deployment/race_day_evening_functional_test.py --force --no-autofix
```

ログ: `logs/race_day_evening_functional_test_YYYYMMDD_HHMMSS.json`

## Windows LAN からの配置

```powershell
cd tools\yokuumakun_race_day_evening_functional_test
.\deploy_from_windows.ps1
```

## 単体テスト（開発用）

```bash
cd tools/yokuumakun_race_day_evening_functional_test
python3 -m unittest test_race_day_evening_functional_test.py -v
```

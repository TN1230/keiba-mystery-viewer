# 一斉予想 → テスト webhook 送信フィルタ

`DISCORD_WEBHOOK_TEST_ALWAYS`（テスト用 Discord webhook）へ送る**一斉予想の動作ログ**を、次だけに制限します。

| 種別 | イベント例 |
|------|------------|
| 開始 | `morning_bulk_worker_start`, `morning_bulk_spawn`, `admin_morning_bulk_rerun` |
| エラー | `morning_bulk_worker_fatal`, `morning_bulk_quality_*`, `morning_bulk_odds_suspicion_modem_reboot`, および `status=error/fatal` |
| 終了 | `morning_bulk_worker_done` |

正常稼働中の中間ログ（キャッシュ flush 等）はテスト webhook に送りません。  
`DISCORD_WEBHOOK_URL_1` / `_3` など本番向け webhook の送信内容は変更しません。

## サーバーへ入れる（推奨・ワンライナー）

```bash
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-test-webhook-filter-19c2/tools/yokuumakun_morning_bulk_test_webhook_filter/bootstrap_on_server.sh | bash
```

## Windows（LAN）から

```powershell
cd C:\path\to\keiba-mystery-viewer\tools\yokuumakun_morning_bulk_test_webhook_filter
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

## ローカルテスト

```bash
python3 -m unittest tools/yokuumakun_morning_bulk_test_webhook_filter/test_morning_bulk_test_webhook_filter.py -v
```

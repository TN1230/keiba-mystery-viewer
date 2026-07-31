# netkeiba アクセス試験（サーバー側）

管理画面「② アクセス試験」用のサーバー実装です。

## 配置先

`/opt/yokuumakun_auto-x/`（yokuumakun_auto-x）

## セットアップ

```bash
cd /opt/yokuumakun_auto-x
# このディレクトリのファイルをコピーしたうえで:
python3 install_into_admin_panel.py /opt/yokuumakun_auto-x
```

`.env` にテスト用 Discord Webhook を追加:

```env
DISCORD_WEBHOOK_TEST=https://discord.com/api/webhooks/...
```

（別名: `ADMIN_TEST_WEBHOOK_URL` / `HWM_DISCORD_WEBHOOK_TEST`）

```bash
sudo systemctl restart yokuum-admin-panel.service
```

## API

`POST /admin/netkeiba-access-test`（Bearer 認証）

- 当日のレース一覧と出馬表へ HTTP アクセス
- 403/429/WAF 文言などを拒否として判定
- 結果をテスト用 Webhook へ通知
- `logs/admin_ops.jsonl` にも記録

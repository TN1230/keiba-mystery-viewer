# 一斉予想成功後の公開 snapshot 漏れ修正

## 原因
朝一斉ワーカーは品質OKでも `_publish_public_viewer_snapshot` を呼んでおらず、閲覧サイト `snapshots/latest.json` が前日クリアのまま残ることがある。  
（2026-08-01 は 07:09 / 07:52 に 36/36 成功したが公開未反映）

## 修正内容
1. `morning_bulk_server_worker.py` — 品質OK完了時に publish
2. `POST /admin/publish-public-snapshot` — キャッシュから強制公開
3. `force_publish_public_snapshot.py` — CLI で即時公開

## サーバーで今すぐ直す＋公開する

```bash
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/morning-bulk-publish-fix-19c2/tools/yokuumakun_morning_bulk_publish_fix/bootstrap_on_server.sh | bash
```

Windows (LAN):

```powershell
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

# 閲覧サイト強制公開 + 明日以降の自動公開（LAN / サーバー直実行）

## 今週空だった理由
1. 朝一斉は成功しても、成功パスが `snapshots/latest.json` を更新していなかった。
2. さらに `build_public_snapshot(..., day_rows=None)` だと **会場殻だけ**（`race_count=0`）が出ることがある。本ツールは cache から `day_rows` を組んで再 publish し、`race_count=0` は失敗扱いする。

## このツールが入れるもの
1. **今すぐ** キャッシュから `latest.json` を強制公開（空 snapshot は成功にしない）
2. **朝一斉ワーカー**成功時に自動 publish（恒久パッチ）
3. **systemd timer**（05:30–11:00）で、完了済みなのに latest が空なら再 publish（保険）
4. admin の `IndentationError` 時はバックアップから自動復旧

## サーバーで実行（推奨）
```bash
export YOKUMAKUN_SUDO_PASS='83670824'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/lan-site-publish-19c2/tools/yokuumakun_lan_site_publish/bootstrap_on_server.sh | bash | tee /tmp/lan_site_publish.log
```

## Windows LAN（先週と同じ paramiko）
```powershell
cd tools\yokuumakun_lan_site_publish
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

## 成功確認
```bash
curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json | head -c 400
systemctl is-enabled yokuum-morning-publish-watch.timer
```

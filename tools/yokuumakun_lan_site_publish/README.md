# 閲覧サイト強制公開（LAN / サーバー直実行）

## 今週サイトが空のままな理由

- **予想自体は成功している**（例: 2026-08-01 10:40 `morning_bulk_done` 36/36 `quality_ok: true`）
- しかし朝一斉ワーカーの**成功パスが `snapshots/latest.json` を更新していなかった**
- 先週見えていた更新は、主に UI/自動予想側の `_publish_public_viewer_snapshot` や開催終了処理側からだった
- 開催終了で `latest.json` は空（cleared）に戻る。今朝の一斉成功後に再 publish が無かったため空のまま

クラウドや SSH インターネット公開は、この公開漏れとは別問題です。

## 推奨: 先週と同じ Windows LAN + paramiko

自宅 LAN 上の Windows で:

```powershell
cd <この tools\yokuumakun_lan_site_publish>
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

接続先は従来どおり `tn@192.168.128.178`、パスワードは `Desktop\ローカルサーバーIP.txt` の `pass:`。

## サーバー上で直接

```bash
export YOKUMAKUN_SUDO_PASS='（SSHと同じパスワード）'
curl -fsSL https://cdn.jsdelivr.net/gh/t-orz/keiba-mystery-viewer@cursor/lan-site-publish-19c2/tools/yokuumakun_lan_site_publish/bootstrap_on_server.sh | bash
```

## 成功確認

```bash
curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json | head -c 400
```

`schedule_date` が当日、`race_count` > 0、`cleared` が無いこと。

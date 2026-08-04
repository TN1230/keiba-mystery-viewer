# 閲覧サイト自動公開の復旧

`latest.json` が `cleared` / レース0のまま更新されないときに、原因切り分けと応急公開を行います。

## サーバーで実行

```bash
cd /tmp
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/viewer-publish-recovery-19c2/tools/yokuumakun_viewer_publish_recovery/recover_viewer_publish_now.sh -o recover_viewer_publish_now.sh
chmod +x recover_viewer_publish_now.sh
export YOKUMAKUN_ROOT=/opt/yokuumakun_auto-x
bash ./recover_viewer_publish_now.sh
```

## 見方

- `cache_ok=0` → 当日の朝一斉キャッシュが無い（公開以前に予想未完了）
- `force_publish rc=0` かつ AFTER の `race_count>0` → 公開復旧成功
- automation が inactive ならスクリプトが起動を試行します

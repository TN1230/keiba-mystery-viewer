# 閲覧サイト強制公開 + 朝一斉/直前予想あとの自動公開（LAN / サーバー直実行）

## 今週空だった理由 / 本日の取りこぼし
1. 朝一斉は成功しても、成功パスが `snapshots/latest.json` を更新していなかった。
2. `build_public_snapshot(..., day_rows=None)` だと **会場殻だけ**（`race_count=0`）が出ることがある。
3. **本日(2026-08-01)の直前成功パターン**: 発走約15分前に `pre_race_auto_predict_worker` が
   `update_races_cache_entry` まで成功（公開上は札幌4〜9Rの `predicted_at` が更新済み）。
   しかしその後 publish が止まり、札幌10R以降が朝一斉のまま残った。

## このツールが入れるもの
1. **今すぐ** キャッシュから `latest.json` を強制公開（空 snapshot は成功にしない）
2. **朝一斉ワーカー**成功時に自動 publish（恒久パッチ）
3. **直前予想ワーカー**成功時（`update_races_cache_entry` 直後）に自動 publish（恒久パッチ）
4. **systemd timer**（05:30–19:00）で
   - latest が空/前日
   - またはキャッシュの `predicted_at` が公開より新しい
   - または直前窓のレースが朝の予想のまま
   なら再 publish
5. admin の `IndentationError` 時はバックアップから自動復旧

## 今すぐレースをサイトへ反映 / 品質修復（最短）
```bash
export YOKUMAKUN_SUDO_PASS='83670824'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/fix-viewer-publish-19c2/tools/yokuumakun_lan_site_publish/repair_and_publish.sh | bash
```

成功時は `QUALITY_OK` と、偏差が小数1桁・ホームズ指数がレースごとに異なる・出馬表が推定3着内率順、を確認。

ホームズ指数は公式経路で Edge `day_rows.best_score` → `_holmes_public_fields` 経由で埋まる（前週 `2026-07-26.json` が良品参照）。
`official_republish_from_cache.py` はサーバーの `build_public_snapshot(*, races, day_rows, schedule_date)` シグネチャに合わせて呼び出す。
gate の `score=25` や壊れた日の定数 `5` はホームズ指数として採用しない。

`repair_and_publish.sh` は正式 publish（hwm ヘルパー）を先に試し、品質 OK なら standalone で上書きしない。
一斉予想の再取得は、キャッシュ自体に `prediction` が無い場合のみ有効。公開品質の問題は publish 経路の修正で足りることが多い。

## サーバーで実行（恒久パッチ込み）
```bash
export YOKUMAKUN_SUDO_PASS='83670824'
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/fix-viewer-publish-19c2/tools/yokuumakun_lan_site_publish/bootstrap_on_server.sh | bash | tee /tmp/lan_site_publish.log
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
# 直前反映: 直近発走レースの predicted_at が朝一斉(10時台)ではなく発走約15分前になっていること
```

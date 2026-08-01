# 展開シミュレーションを管理画面から開く（一時）

管理画面「④ 展開シミュレーション起動」から、会場タブ／Rジャンプ（または race_id 直指定）で
別タブに `GET /tenkai` の展開シミュレーションを開きます。

## 必要なもの（2段階）

1. **Pages 管理画面**（このブランチ／PR の `admin/*` + `config.js`）
2. **LAN サーバー**に `race_progression_sim.py` と `GET /tenkai`（下記 deploy）

いま `/tenkai` が 404 のときは、まだサーバー側が未導入です。

## Windows（LAN・推奨）

メイン機に `Desktop\yokuumakun\race_progression_sim.py` がある状態で:

```powershell
cd tools\yokuumakun_tenkai_sim_launch
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

やること:

1. `yokuumakun` から sim 本体と依存モジュールを `/opt/yokuumakun_auto-x` へコピー
2. `admin_panel_api.py` に `GET /tenkai` を組み込み
3. `admin_api.json` に `tenkai_sim_url_template` を追記
4. `yokuum-admin-panel.service` を再起動

## サーバー直実行

```bash
export YOKUMAKUN_SUDO_PASS='…'
# ソースが分かるとき:
export YOKUMAKUN_SIM_SOURCE='/home/tn/yokuumakun'   # または Desktop 相当パス
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/admin-tenkai-sim-launch-19c2/tools/yokuumakun_tenkai_sim_launch/bootstrap_on_server.sh | bash
```

## 確認

```bash
# エンドポイント
curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8791/tenkai?race_id=probe'
# discovery
curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/admin_api.json | python3 -m json.tool | head -20
```

管理画面: ログイン →「④ 展開シミュレーション起動」→ レースボタン、または race_id 直指定。

## 削除時

`TEMP: TENKAI_SIM_LAUNCH` マーカー付きの viewer/admin 変更を消し、サーバーでは:

```bash
python3 /opt/yokuumakun_auto-x/_tenkai_sim_install/install_tenkai_endpoint.py /opt/yokuumakun_auto-x --uninstall
sudo systemctl restart yokuum-admin-panel.service
```

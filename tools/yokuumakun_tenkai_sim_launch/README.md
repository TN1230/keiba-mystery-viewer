# 展開シミュレーションを auto-x に載せる（一時）

管理画面「③ 展開シミュレーション起動」が別タブで開く先を、管理APIと同じオリジンの `GET /tenkai` に揃えます。

機能本体（`race_progression_sim.py` など）が `/opt/yokuumakun_auto-x` に無い場合は、メイン機の `yokuumakun` からコピーします。

## Windows（LAN・推奨）

```powershell
cd tools\yokuumakun_tenkai_sim_launch
powershell -ExecutionPolicy Bypass -File deploy_from_windows.ps1
```

やること:

1. `C:\Users\mocco\Desktop\yokuumakun` から `race_progression_sim.py` と不足モジュールを `/opt/yokuumakun_auto-x` へコピー
2. `admin_panel_api.py` に `GET /tenkai` を組み込み
3. `admin_api.json` に `tenkai_sim_url_template` を追記（Pages の管理画面がそれを読む）
4. `yokuum-admin-panel.service` を再起動

## サーバー直実行

ソースがサーバー上の別ツリーにある場合:

```bash
export YOKUMAKUN_SUDO_PASS='…'
export YOKUMAKUN_SIM_SOURCE='/path/to/yokuumakun'   # 省略時は候補を自動探索
curl -fsSL https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/admin-tenkai-sim-launch-19c2/tools/yokuumakun_tenkai_sim_launch/bootstrap_on_server.sh | bash | tee /tmp/tenkai_sim_bootstrap.log
```

## 確認

```bash
curl -sS "$(curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/admin_api.json | python3 -c 'import sys,json;print(json.load(sys.stdin)["base_url"])')/tenkai?race_id=test" | head
```

discovery に `tenkai_sim_url_template` が入っていれば、`config.js` の `TENKAI_SIM_URL_TEMPLATE` は空のままでOKです。

## 削除時

`TEMP: TENKAI_SIM_LAUNCH` マーカー付きの viewer/admin 変更を消し、サーバーでは:

```bash
python3 /opt/yokuumakun_auto-x/_tenkai_sim_install/install_tenkai_endpoint.py /opt/yokuumakun_auto-x --uninstall
sudo systemctl restart yokuum-admin-panel.service
```

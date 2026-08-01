#!/usr/bin/env bash
# サーバー上で実行: メイン機 yokuumakun 相当ツリーから sim をコピーし GET /tenkai を有効化
# 例:
#   export YOKUMAKUN_SUDO_PASS='…'
#   export YOKUMAKUN_SIM_SOURCE='/home/tn/yokuumakun'   # 任意
#   bash bootstrap_on_server.sh
set -euo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/admin-tenkai-sim-launch-19c2}"
BASE="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_tenkai_sim_launch"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

cd "$TMP"
for f in copy_sim_from_yokuumakun.py tenkai_sim_gateway.py install_tenkai_endpoint.py publish_tenkai_discovery.py; do
  curl -fsSL -o "$f" "$BASE/$f"
done

mkdir -p "$ROOT/_tenkai_sim_install"
cp -f ./*.py "$ROOT/_tenkai_sim_install/"

SOURCE_ARGS=()
if [[ -n "${YOKUMAKUN_SIM_SOURCE:-}" ]]; then
  SOURCE_ARGS=(--source "$YOKUMAKUN_SIM_SOURCE")
fi

# ソースが取れるときだけコピー（既に ROOT にあれば help だけでも先へ進める）
if [[ -n "${YOKUMAKUN_SIM_SOURCE:-}" || -f /home/tn/yokuumakun/race_progression_sim.py || -f /opt/yokuumakun/race_progression_sim.py || -f "$ROOT/race_progression_sim.py" ]]; then
  python3 "$ROOT/_tenkai_sim_install/copy_sim_from_yokuumakun.py" "${SOURCE_ARGS[@]}" --dest "$ROOT" --force || true
else
  echo "WARN: race_progression_sim.py のソース候補がありません。エンドポイントのみ入れます。"
fi

python3 "$ROOT/_tenkai_sim_install/install_tenkai_endpoint.py" "$ROOT"
cd "$ROOT"
.venv/bin/python -m py_compile admin_panel_api.py tenkai_sim_gateway.py

if [[ -n "${YOKUMAKUN_SUDO_PASS:-}" ]]; then
  echo "$YOKUMAKUN_SUDO_PASS" | sudo -S -p '' systemctl restart yokuum-admin-panel.service
else
  sudo systemctl restart yokuum-admin-panel.service
fi
sleep 1
systemctl is-active yokuum-admin-panel.service
code="$(curl -sS -o /tmp/tenkai_probe.html -w '%{http_code}' 'http://127.0.0.1:8791/tenkai?race_id=probe' || true)"
echo "tenkai_http=$code"
head -c 240 /tmp/tenkai_probe.html || true
echo

YOKUMAKUN_ROOT="$ROOT" "$ROOT/.venv/bin/python" "$ROOT/_tenkai_sim_install/publish_tenkai_discovery.py" || {
  echo "WARN: discovery 更新に失敗（.env の Supabase キーを確認）"
}

curl -fsSL https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/admin_api.json | head -c 500
echo
echo "DONE: GET /tenkai ready (TEMP: TENKAI_SIM_LAUNCH)"

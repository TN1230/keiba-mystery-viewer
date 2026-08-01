#!/usr/bin/env bash
# 最短修復: admin 復旧 + キャッシュからサイトへレース反映
set -uo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/lan-site-publish-19c2}"
BASE_RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_lan_site_publish"

cd "$ROOT" || exit 1

if [[ -f admin_panel_api.py.bak_publish_endpoint ]]; then
  cp -f admin_panel_api.py.bak_publish_endpoint admin_panel_api.py
  echo "restored admin_panel_api.py from bak_publish_endpoint"
fi

curl -fsSL -o force_publish_public_snapshot.py "$BASE_RAW/force_publish_public_snapshot.py"
curl -fsSL -o standalone_publish_from_cache.py "$BASE_RAW/standalone_publish_from_cache.py"

echo "=== standalone publish (direct from morning_bulk cache) ==="
.venv/bin/python standalone_publish_from_cache.py | tee /tmp/standalone_publish.json
echo "standalone rc=${PIPESTATUS[0]}"

echo "=== latest.json ==="
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("schedule_date"), "race_count=", d.get("race_count"), "updated_at=", d.get("updated_at")); print([(v.get("place"), len(v.get("races") or [])) for v in d.get("venues") or []])'

# admin 再起動（任意）
if systemctl list-unit-files yokuum-admin-panel.service 2>/dev/null | grep -q yokuum-admin-panel; then
  if [[ -n "${YOKUMAKUN_SUDO_PASS:-}" ]]; then
    echo "$YOKUMAKUN_SUDO_PASS" | sudo -S -p '' systemctl restart yokuum-admin-panel.service || true
  else
    sudo systemctl restart yokuum-admin-panel.service || true
  fi
fi

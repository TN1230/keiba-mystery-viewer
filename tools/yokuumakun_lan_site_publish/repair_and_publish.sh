#!/usr/bin/env bash
# 品質修復: 正式 publish 経路 → 改善 standalone → 検証
# 一斉予想の再取得は、キャッシュに prediction が無い/壊れている場合のみ有効。
set -uo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/lan-site-publish-19c2}"
BASE_RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_lan_site_publish"

cd "$ROOT" || exit 1

if [[ -f admin_panel_api.py.bak_publish_endpoint ]]; then
  if ! .venv/bin/python -m py_compile admin_panel_api.py 2>/dev/null; then
    cp -f admin_panel_api.py.bak_publish_endpoint admin_panel_api.py
    echo "restored admin_panel_api.py from bak_publish_endpoint"
  fi
fi

for f in \
  force_publish_public_snapshot.py \
  standalone_publish_from_cache.py \
  official_republish_from_cache.py
do
  curl -fsSL -o "$f" "$BASE_RAW/$f" || echo "WARN: download failed $f"
done

echo "=== 1) official republish (day_rows / hwm helpers) ==="
set +e
.venv/bin/python official_republish_from_cache.py | tee /tmp/official_republish.json
OFF_RC=${PIPESTATUS[0]}
echo "official rc=$OFF_RC"

echo "=== 2) improved standalone (quality fields) ==="
.venv/bin/python standalone_publish_from_cache.py | tee /tmp/standalone_publish.json
ST_RC=${PIPESTATUS[0]}
echo "standalone rc=$ST_RC"
set -e

echo "=== latest.json quality ==="
curl -fsSL "https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json" \
  | python3 - <<'PY'
import sys, json
d=json.load(sys.stdin)
print(d.get("schedule_date"), "race_count=", d.get("race_count"), "updated_at=", d.get("updated_at"))
print("venues", [(v.get("place"), len(v.get("races") or [])) for v in d.get("venues") or []])
missing_h=long_dev=watson_blank=third_blank=umabanish=0
n=0
for v in d.get("venues") or []:
  for r in v.get("races") or []:
    n+=1
    if not r.get("holmes_index"): missing_h+=1
    dev=r.get("dev")
    if isinstance(dev, float) and len(str(dev))>6: long_dev+=1
    marks=r.get("marks") or {}
    if marks.get("ワ") in (None,"","-"): watson_blank+=1
    cells=r.get("cells") or {}
    if (marks.get("ハ/ホプ") in (None,"","-")) and (cells.get("ハ/ホプ") in (None,"","-")):
      third_blank+=1
    rows=(r.get("shutuba") or {}).get("rows") or []
    umas=[str(x.get("馬番")) for x in rows[:4]]
    if umas and umas==sorted(umas, key=lambda x: int(x) if x.isdigit() else 99):
      umabanish+=1
r0=((d.get("venues") or [{}])[0].get("races") or [None])[0]
if r0:
  print("sample", r0.get("place"), r0.get("R"), "dev", r0.get("dev"), "holmes", r0.get("holmes_index"), "best", r0.get("best_logic"))
  print("marks", r0.get("marks"))
  print("cells", r0.get("cells"))
  rows=(r0.get("shutuba") or {}).get("rows") or []
  print("shutuba_order", [x.get("馬番") for x in rows[:6]], "first_place_pct", (rows[0] or {}).get("推定3着内率") if rows else None)
print(f"quality missing_holmes={missing_h}/{n} long_dev={long_dev} watson_blank={watson_blank} third_blank={third_blank} umaban_orderish={umabanish}")
if missing_h==0 and long_dev==0 and n>0:
  print("QUALITY_OK")
else:
  print("QUALITY_NEEDS_ATTENTION")
  print("NOTE: 一斉予想の再取得は prediction 欠落時のみ有効。先に ops/publish_helpers_dump.json を確認。")
PY

# admin restart optional
if systemctl list-unit-files yokuum-admin-panel.service 2>/dev/null | grep -q yokuum-admin-panel; then
  if [[ -n "${YOKUMAKUN_SUDO_PASS:-}" ]]; then
    echo "$YOKUMAKUN_SUDO_PASS" | sudo -S -p '' systemctl restart yokuum-admin-panel.service || true
  fi
fi

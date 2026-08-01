#!/usr/bin/env bash
# 品質修復: 正式 publish 経路 →（必要時のみ）改善 standalone → 検証
# 一斉予想の再取得は、キャッシュに prediction が無い/壊れている場合のみ有効。
set -uo pipefail
ROOT="${YOKUMAKUN_ROOT:-/opt/yokuumakun_auto-x}"
BRANCH="${1:-cursor/race-summary-pace-label-19c2}"
BASE_RAW="https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/${BRANCH}/tools/yokuumakun_lan_site_publish"
LATEST_URL="https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json"

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

check_latest_quality() {
  # heredoc は stdin を食うので、先にファイルへ落としてから検査する
  local out="/tmp/latest_quality_check.json"
  if ! curl -fsSL "$LATEST_URL" -o "$out"; then
    echo "QUALITY_FETCH_FAILED"
    return 2
  fi
  .venv/bin/python - "$out" <<'PY'
import json, sys, re
from collections import Counter
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
print(d.get("schedule_date"), "race_count=", d.get("race_count"), "updated_at=", d.get("updated_at"))
print("venues", [(v.get("place"), len(v.get("races") or [])) for v in d.get("venues") or []])
races = []
for v in d.get("venues") or []:
    races.extend(v.get("races") or [])
n = len(races)
missing_h = long_dev = watson_blank = third_blank = umabanish = 0
holmes_nums = []
watson_cells = []
irene_cells = []
for r in races:
    hi = str(r.get("holmes_index") or "").strip()
    m = re.match(r"([0-9]+(?:\.[0-9]+)?)", hi)
    if not m:
        missing_h += 1
    else:
        holmes_nums.append(m.group(1))
    dev = r.get("dev")
    if isinstance(dev, float):
        s = f"{dev:.10f}".rstrip("0")
        if "." in s and len(s.split(".")[-1]) > 1:
            long_dev += 1
    elif isinstance(dev, str) and "." in dev and len(dev.split(".")[-1]) > 1:
        long_dev += 1
    marks = r.get("marks") or {}
    if marks.get("ワ") in (None, "", "-"):
        watson_blank += 1
    if marks.get("ハ/ホプ") in (None, "", "-"):
        third_blank += 1
    cells = r.get("cells") or {}
    wc = str(cells.get("ワ") or "").strip()
    ic = str(cells.get("アイ") or "").strip()
    if wc and wc != "-":
        watson_cells.append(wc)
    if ic and ic != "-":
        irene_cells.append(ic)
    rows = (r.get("shutuba") or {}).get("rows") or []
    umas = [str(x.get("馬番")) for x in rows[:4]]
    if umas and umas == sorted(umas, key=lambda x: int(x) if x.isdigit() else 99):
        umabanish += 1
identical = len(set(holmes_nums)) <= 1 and n >= 3 and missing_h == 0
identical_watson = len(set(watson_cells)) <= 1 and len(watson_cells) >= max(8, n // 2)
identical_irene = len(set(irene_cells)) <= 1 and len(irene_cells) >= max(8, n // 2)
placeholder_cells = (
    identical_watson and watson_cells[:1] == ["様子・中位帯"]
) or (identical_irene and irene_cells[:1] == ["様子・様子見"])
long_sui = blank_sui = 0
sui_vals = []
for v in d.get("venues") or []:
    for m in v.get("matrix") or []:
        sui = str((m or {}).get("sui") or "").strip()
        if not sui or sui == "-":
            blank_sui += 1
        else:
            sui_vals.append(sui)
        if "（" in sui or "(" in sui or sui in {"watson", "irene", "hunter", "moriarty", "hope"}:
            long_sui += 1
r0 = races[0] if races else None
if r0:
    rows = (r0.get("shutuba") or {}).get("rows") or []
    print(
        "sample",
        r0.get("place"),
        r0.get("R"),
        "dev",
        r0.get("dev"),
        "holmes",
        r0.get("holmes_index"),
        "best",
        r0.get("best_logic"),
    )
    print("marks", r0.get("marks"))
    print("cells", r0.get("cells"))
    print(
        "shutuba_order",
        [x.get("馬番") for x in rows[:6]],
        "first_place_pct",
        (rows[0] or {}).get("推定3着内率") if rows else None,
    )
print(
    f"quality missing_holmes={missing_h}/{n} long_dev={long_dev} "
    f"identical_holmes={identical} watson_blank={watson_blank} "
    f"third_blank={third_blank} umaban_orderish={umabanish} "
    f"identical_watson_cells={identical_watson} identical_irene_cells={identical_irene} "
    f"placeholder_cells={placeholder_cells} long_sui={long_sui} blank_sui={blank_sui}"
)
if holmes_nums:
    print("holmes_top", Counter(holmes_nums).most_common(8))
if watson_cells:
    print("watson_cells_top", Counter(watson_cells).most_common(6))
if irene_cells:
    print("irene_cells_top", Counter(irene_cells).most_common(6))
if sui_vals:
    print("sui_top", Counter(sui_vals).most_common(8))
ok = (
    n > 0
    and missing_h == 0
    and long_dev == 0
    and not identical
    and umabanish == 0
    and not identical_watson
    and not identical_irene
    and not placeholder_cells
    and long_sui == 0
    and blank_sui == 0
)
if ok:
    print("QUALITY_OK")
    raise SystemExit(0)
print("QUALITY_NEEDS_ATTENTION")
print("NOTE: 一斉予想の再取得は prediction 欠落時のみ有効。正式 publish ヘルパー優先。")
raise SystemExit(1)
PY
}

echo "=== 1) official republish (day_rows / hwm helpers) ==="
set +e
.venv/bin/python official_republish_from_cache.py | tee /tmp/official_republish.json
OFF_RC=${PIPESTATUS[0]}
echo "official rc=$OFF_RC"

echo "=== quality after official ==="
check_latest_quality
Q1_RC=$?
echo "quality1 rc=$Q1_RC"

if [[ "$OFF_RC" -eq 0 && "$Q1_RC" -eq 0 ]]; then
  echo "SKIP standalone: official publish already QUALITY_OK"
  ST_RC=0
else
  echo "=== 2) improved standalone (quality fields) ==="
  .venv/bin/python standalone_publish_from_cache.py | tee /tmp/standalone_publish.json
  ST_RC=${PIPESTATUS[0]}
  echo "standalone rc=$ST_RC"
  echo "=== quality after standalone ==="
  check_latest_quality
  Q2_RC=$?
  echo "quality2 rc=$Q2_RC"
fi
set -e

# admin restart optional
if systemctl list-unit-files yokuum-admin-panel.service 2>/dev/null | grep -q yokuum-admin-panel; then
  if [[ -n "${YOKUMAKUN_SUDO_PASS:-}" ]]; then
    echo "$YOKUMAKUN_SUDO_PASS" | sudo -S -p '' systemctl restart yokuum-admin-panel.service || true
  fi
fi

# PDF ホームズ指数欠落の修復（サーバー）

## 症状
閲覧サイトの `holmes_index` は出ているが、予想詳細PDFヘッダが次のようになる:

```text
ホームズ指数:- / 当日レース内順位:算出前
```

前週PDFは `ホームズ指数:78` 等が入っていた（順位は当時 `1位/1レース中` のこともあった）。

## 原因
印付き出馬表PDFは `hwm.py` の `_export_marked_syutsuba_pdf_with_meta` が生成する。
直前ワーカー等のサブプロセスでは day holmes snap / 指数解決が空のままヘッダを書いていた。

## 適用（サーバー）
```bash
export YOKUMAKUN_ROOT=/opt/yokuumakun_auto-x
cd /tmp
curl -fsSL -O https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/pdf-holmes-index-fix-19c2/tools/yokuumakun_pdf_holmes_fix/patch_pdf_holmes_index.py
curl -fsSL -O https://raw.githubusercontent.com/t-orz/keiba-mystery-viewer/cursor/pdf-holmes-index-fix-19c2/tools/yokuumakun_pdf_holmes_fix/regenerate_race_pdfs.py
cd /opt/yokuumakun_auto-x
.venv/bin/python /tmp/patch_pdf_holmes_index.py /opt/yokuumakun_auto-x
.venv/bin/python /tmp/regenerate_race_pdfs.py
```

## 確認
```bash
# 直近PDFのヘッダに ホームズ指数:NN が出ること
curl -fsSL "$(python3 - <<'PY'
import json,urllib.request
d=json.load(urllib.request.urlopen('https://rathgwvfewasazxlpusx.supabase.co/storage/v1/object/public/public-viewer/snapshots/latest.json'))
for v in d['venues']:
  for r in v['races']:
    if r.get('pdf_url'):
      print(r['pdf_url']); raise SystemExit
PY
)" -o /tmp/one.pdf
pdftotext -layout /tmp/one.pdf - | head -8
```

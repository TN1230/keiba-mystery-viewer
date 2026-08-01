#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwm.py の印付き出馬表PDFヘッダでホームズ指数が '-' になる問題をパッチする。

戦略:
1. `_pdf_resolve_holmes_for_export` ヘルパーを hwm.py に注入
2. `_export_marked_syutsuba_pdf_with_meta` 内のヘッダ用スコア/順位解決をヘルパー経由に置換
3. ヘッダ文字列が古い変数のままでも動くよう、解決結果を race_info にも書き戻す
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BEGIN_HELPER = "# BEGIN pdf_holmes_resolve_helper"
END_HELPER = "# END pdf_holmes_resolve_helper"
BEGIN_INJECT = "# BEGIN pdf_holmes_resolve_inject"
END_INJECT = "# END pdf_holmes_resolve_inject"

HELPER = f'''
{BEGIN_HELPER}
def _pdf_resolve_holmes_for_export(rid: str, race_info: dict | None) -> tuple[str, str]:
    """PDFヘッダ用のホームズ指数・当日順位。空なら ('-', '算出前')。"""
    info = race_info if isinstance(race_info, dict) else {{}}
    rid_s = str(rid or "").strip()

    def _fmt_score(v) -> str | None:
        if v is None or v == "":
            return None
        try:
            x = float(v)
        except Exception:
            s = str(v).strip()
            return s if s and s not in {{"-", "None", "nan"}} else None
        if x != x:
            return None
        # gate の 25 など別用途は除外（公開側と同じ方針）
        if x < 40.0 or x > 100.0:
            return None
        if abs(x - round(x)) < 1e-6:
            return str(int(round(x)))
        return f"{{x:.1f}}".rstrip("0").rstrip(".")

    # 1) 正式ヘルパー（day snap / 上書き込み）
    try:
        score_txt, rank_txt = _holmes_index_score_and_rank_texts(rid_s, info)  # type: ignore[name-defined]
        sc = _fmt_score(score_txt) if score_txt is not None else None
        if sc:
            rt = str(rank_txt or "").strip() or "算出前"
            return sc, rt
    except Exception:
        pass

    # 2) day snap 直接
    score = None
    try:
        snap = _load_day_holmes_score_snap() or {{}}  # type: ignore[name-defined]
        for bucket in ("latest_scores", "morning_scores", "scores"):
            mp = snap.get(bucket) or {{}}
            if rid_s in mp:
                score = mp.get(rid_s)
                break
            if rid_s.isdigit() and int(rid_s) in mp:
                score = mp.get(int(rid_s))
                break
    except Exception:
        pass

    # 3) race_info 上の候補（ゲート snap の雑 walk はしない）
    if score is None:
        for key in (
            "morning_holmes_best_score",
            "holmes_index",
            "holmes_score",
            "morning_holmes_index",
        ):
            if key in info and info.get(key) not in (None, "", "-"):
                score = info.get(key)
                break

    sc = _fmt_score(score)
    if not sc:
        return "-", "算出前"

    # 順位: 上書き適用後に再取得、だめなら算出前
    rank_txt = "算出前"
    try:
        _apply_day_holmes_rank_overrides_to_race_info(info)  # type: ignore[name-defined]
    except Exception:
        pass
    try:
        _score2, rank2 = _holmes_index_score_and_rank_texts(rid_s, info)  # type: ignore[name-defined]
        if rank2:
            rank_txt = str(rank2).strip() or rank_txt
        sc2 = _fmt_score(_score2)
        if sc2:
            sc = sc2
    except Exception:
        pass
    # race_info へも書いて後続ロジックと公開側を寄せる
    try:
        info["holmes_index"] = sc
        info["holmes_rank_text"] = rank_txt
    except Exception:
        pass
    return sc, rank_txt
{END_HELPER}
'''


def _strip_block(text: str, begin: str, end: str) -> str:
    return re.sub(
        rf"[ \t]*{re.escape(begin)}[\s\S]*?{re.escape(end)}\n?",
        "",
        text,
    )


def _inject_helper(text: str) -> str:
    text = _strip_block(text, BEGIN_HELPER, END_HELPER)
    # PDF export の直前にヘルパーを置く
    m = re.search(r"\ndef _export_marked_syutsuba_pdf_with_meta\(", text)
    if not m:
        raise SystemExit("anchor _export_marked_syutsuba_pdf_with_meta not found")
    return text[: m.start()] + "\n" + HELPER + text[m.start() :]


def _inject_resolve_call(text: str) -> str:
    text = _strip_block(text, BEGIN_INJECT, END_INJECT)
    # race_info 確定直後
    m = re.search(
        r"(?m)^(?P<ind>[ \t]*)if not race_info:\n"
        r"(?P=ind)[ \t]*return None, \"\"\n",
        text,
    )
    if not m:
        # 別スタイル
        m = re.search(
            r"(?m)^(?P<ind>[ \t]*)if not race_info:\n"
            r"(?P=ind)[ \t]*return None, ''\n",
            text,
        )
    if not m:
        raise SystemExit("anchor `if not race_info: return None` not found in hwm.py")

    ind = m.group("ind")
    block = (
        f"{ind}{BEGIN_INJECT}\n"
        f"{ind}try:\n"
        f"{ind}    _pdf_holmes_score_txt, _pdf_holmes_rank_txt = _pdf_resolve_holmes_for_export(rid, race_info)\n"
        f"{ind}except Exception:\n"
        f"{ind}    _pdf_holmes_score_txt, _pdf_holmes_rank_txt = \"-\", \"算出前\"\n"
        f"{ind}{END_INJECT}\n"
    )
    return text[: m.end()] + block + text[m.end() :]


def _rewrite_header_line(text: str) -> tuple[str, int]:
    """ヘッダ生成行の指数/順位プレースホルダを解決済み変数へ寄せる。"""
    n = 0

    # パターンA: f"...ホームズ指数:{expr} / 当日レース内順位:{expr2}..."
    def repl_f(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        s = m.group(0)
        s2 = re.sub(
            r"ホームズ指数:\{[^}]+\}",
            "ホームズ指数:{_pdf_holmes_score_txt}",
            s,
            count=1,
        )
        s2 = re.sub(
            r"当日レース内順位:\{[^}]+\}",
            "当日レース内順位:{_pdf_holmes_rank_txt}",
            s2,
            count=1,
        )
        return s2

    text2 = re.sub(
        r"f?[\"'][^\"']*ホームズ指数:[^\"']*当日レース内順位:[^\"']*[\"']",
        repl_f,
        text,
    )

    # パターンB: 変数代入 holmes_* = ... の直後に上書き（関数内のそれっぽい代入）
    # export 関数内だけに限定するため、inject ブロック後〜次の def までを対象
    mfn = re.search(
        r"def _export_marked_syutsuba_pdf_with_meta\([\s\S]*?(?=\ndef )",
        text2,
    )
    if mfn:
        body = mfn.group(0)
        body2 = body
        # よくある代入名を強制上書き
        for pat, var in (
            (
                r"(?m)^(?P<ind>[ \t]*)(holmes_index_text|holmes_score_text|holmes_idx_text|hi_txt)\s*=\s*[^\n]+\n",
                "_pdf_holmes_score_txt",
            ),
            (
                r"(?m)^(?P<ind>[ \t]*)(holmes_rank_text|holmes_rank_txt|hr_txt)\s*=\s*[^\n]+\n",
                "_pdf_holmes_rank_txt",
            ),
        ):
            def _assign_repl(mm: re.Match[str], _var: str = var) -> str:
                nonlocal n
                # すでに pdf resolve なら触らない
                line = mm.group(0)
                if "_pdf_holmes_" in line or BEGIN_INJECT in line:
                    return line
                n += 1
                name = mm.group(2)
                return f"{mm.group('ind')}{name} = {_var}\n"

            body2 = re.sub(pat, _assign_repl, body2)

        # 文字列連結型: "ホームズ指数:" + str(x)
        def repl_concat(mm: re.Match[str]) -> str:
            nonlocal n
            n += 1
            return mm.group(1) + "_pdf_holmes_score_txt" + mm.group(3)

        body2 = re.sub(
            r'(ホームズ指数[:：]\s*"?\s*\+\s*)([^+\n]+)(\s*\+)',
            repl_concat,
            body2,
        )

        def repl_rank_concat(mm: re.Match[str]) -> str:
            nonlocal n
            n += 1
            return mm.group(1) + "_pdf_holmes_rank_txt" + mm.group(3)

        body2 = re.sub(
            r'(当日レース内順位[:：]\s*"?\s*\+\s*)([^+\n]+)(\s*\+)',
            repl_rank_concat,
            body2,
        )

        if body2 != body:
            text2 = text2[: mfn.start()] + body2 + text2[mfn.end() :]

    # パターンC: まだ ホームズ指数:- リテラル固定なら置換
    if "ホームズ指数:-" in text2 and "_pdf_holmes_score_txt" in text2:
        text2 = text2.replace("ホームズ指数:-", "ホームズ指数:{_pdf_holmes_score_txt}")
        n += 1

    return text2, n


def patch(root: Path) -> None:
    root = root.resolve()
    hwm = root / "hwm.py"
    if not hwm.is_file():
        raise SystemExit(f"missing {hwm}")

    text = hwm.read_text(encoding="utf-8", errors="replace")
    if "def _export_marked_syutsuba_pdf_with_meta" not in text:
        raise SystemExit("hwm.py has no _export_marked_syutsuba_pdf_with_meta")

    bak = hwm.with_suffix(hwm.suffix + ".bak_pdf_holmes")
    if not bak.exists():
        shutil.copy2(hwm, bak)
        print(f"backup {bak}")

    text = _inject_helper(text)
    text = _inject_resolve_call(text)
    text, n_re = _rewrite_header_line(text)

    # 最終手段: ヘッダ Paragraph 行に必ず解決変数を使うよう、
    # 「ホームズ指数:」を含む最初の f-string を正規化
    if n_re == 0:
        m = re.search(
            r"(?m)^(?P<ind>[ \t]*)(?P<lhs>\w+\s*=\s*)(?P<q>f?[\"'])(?P<body>[^\"']*ホームズ指数:[^\"']*)(?P=q)",
            text,
        )
        if m:
            body = m.group("body")
            body = re.sub(r"ホームズ指数:[^/]*", "ホームズ指数:{_pdf_holmes_score_txt} ", body, count=1)
            body = re.sub(
                r"当日レース内順位:[^/]*",
                "当日レース内順位:{_pdf_holmes_rank_txt} ",
                body,
                count=1,
            )
            # ensure f-string
            q = m.group("q")
            if not q.startswith("f"):
                q = "f" + q
            repl = f"{m.group('ind')}{m.group('lhs')}{q}{body}{m.group('q')[-1]}"
            text = text[: m.start()] + repl + text[m.end() :]
            n_re = 1
            print("rewrote header assignment line as f-string")

    hwm.write_text(text, encoding="utf-8")
    # syntax check
    compile(text, str(hwm), "exec")
    print(f"patched {hwm} header_rewrites={n_re}")
    if n_re == 0:
        print(
            "WARN: could not find header rewrite target; helper+inject are in place. "
            "Inspect hwm.py around ホームズ指数 and re-run after adjusting patterns."
        )
    # show context
    for i, line in enumerate(text.splitlines(), 1):
        if "ホームズ指数" in line and ("期待値偏差" in line or "当日レース内順位" in line or "_pdf_holmes" in line):
            print(f"L{i}: {line[:220]}")


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "/opt/yokuumakun_auto-x")
    patch(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

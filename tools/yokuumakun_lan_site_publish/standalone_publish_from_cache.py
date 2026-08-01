#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""morning_bulk キャッシュから public snapshot を自前構築して upload する。

build_public_snapshot が会場殻だけ返す場合の最終手段。
サーバー上:
  cd /opt/yokuumakun_auto-x && .venv/bin/python standalone_publish_from_cache.py
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")

FRAME_STYLE = {
    1: ("#FFFFFF", "#000000"),
    2: ("#000000", "#FFFFFF"),
    3: ("#FF0000", "#FFFFFF"),
    4: ("#0000FF", "#FFFFFF"),
    5: ("#FFFF00", "#000000"),
    6: ("#00FF00", "#000000"),
    7: ("#FFA500", "#000000"),
    8: ("#FFC0CB", "#000000"),
}

LOGIC_LABELS = {
    "watson": "ワトソン",
    "irene": "アイリーン",
    "hunter": "ハンター（夏競馬特化）",
    "moriarty": "モリアーティ",
    "hope": "ホープ",
}


def _root() -> Path:
    env = (os.environ.get("YOKUMAKUN_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    if (here / "hwm.py").is_file():
        return here
    return Path("/opt/yokuumakun_auto-x")


def _load_env(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env", override=False)
        for rel in ("server_deployment/hwm_runtime.env", "server_deployment/.env"):
            p = root / rel
            if p.is_file():
                load_dotenv(p, override=False)
    except Exception:
        pass


def _load_races(root: Path) -> tuple[str, dict[str, Any], list[str]]:
    notes: list[str] = []
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    day = datetime.now(_JST).strftime("%Y-%m-%d")
    try:
        from hwm_server_standalone import (  # type: ignore
            _load_morning_bulk_races_cache,
            effective_schedule_date_iso,
        )

        day = str(effective_schedule_date_iso())
        races = _load_morning_bulk_races_cache(day) or {}
        if races:
            notes.append(f"helper_cache day={day} n={len(races)}")
            return day, races, notes
    except Exception as e:
        notes.append(f"helper_cache err={type(e).__name__}:{e}")

    ymd = day.replace("-", "")
    logs = root / "logs"
    for name in (f"morning_bulk_races_{ymd}.pkl", f"morning_bulk_races_{day}.pkl"):
        fp = logs / name
        if not fp.is_file():
            continue
        with fp.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict) and data:
            notes.append(f"loaded {name} n={len(data)}")
            return day, data, notes

    # newest pkl
    if logs.is_dir():
        cands = sorted(logs.glob("morning_bulk_races_*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for fp in cands[:3]:
            try:
                with fp.open("rb") as f:
                    data = pickle.load(f)
                if isinstance(data, dict) and data:
                    stem = fp.name.replace("morning_bulk_races_", "").replace(".pkl", "")
                    if len(stem) == 8 and stem.isdigit():
                        day = f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}"
                    notes.append(f"loaded newest {fp.name} day={day} n={len(data)}")
                    return day, data, notes
            except Exception:
                continue
    return day, {}, notes


def _info(rinfo: dict[str, Any]) -> dict[str, Any]:
    info = rinfo.get("info")
    return info if isinstance(info, dict) else {}


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _as_records(obj: Any) -> list[dict[str, Any]]:
    if obj is None:
        return []
    try:
        import pandas as pd  # type: ignore

        if isinstance(obj, pd.DataFrame):
            df = obj.where(pd.notnull(obj), None)
            return [{str(k): r[k] for k in r} for r in df.to_dict(orient="records")]
    except Exception:
        pass
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        # already rows?
        if all(isinstance(v, dict) for v in obj.values()):
            return list(obj.values())
    return []


def _format_mark_map(marks: Any) -> str:
    if marks is None:
        return "-"
    if isinstance(marks, str):
        return marks.strip() or "-"
    if not isinstance(marks, dict) or not marks:
        return "-"
    # already public-style keys?
    if any(k in marks for k in ("ワ", "アイ", "ハ/ホプ")):
        return "-"  # handled elsewhere
    order = ["◎", "○", "▲", "△", "☆"]
    parts: list[str] = []
    for sym in order:
        if sym not in marks:
            continue
        v = marks.get(sym)
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, (list, tuple, set)):
            parts.append(sym + ",".join(str(x) for x in v))
        else:
            parts.append(sym + str(v))
    return "".join(parts) if parts else "-"


def _marks_umaban_symbol(marks: Any) -> dict[int, str]:
    """mark map {◎:4, ○:12, △:[6,9]} -> {4:'◎', 12:'○', 6:'△', 9:'△'}"""
    out: dict[int, str] = {}
    if not isinstance(marks, dict):
        return out
    priority = {"◎": 0, "○": 1, "▲": 2, "△": 3, "☆": 4}
    for sym, v in marks.items():
        if sym not in priority:
            continue
        vals = v if isinstance(v, (list, tuple, set)) else [v]
        for item in vals:
            try:
                n = int(item)
            except Exception:
                continue
            prev = out.get(n)
            if prev is None or priority[sym] < priority.get(prev, 99):
                out[n] = sym
    return out


def _get_logic_marks(rinfo: dict[str, Any]) -> dict[str, Any]:
    return {
        "watson": rinfo.get("watson_marks") or rinfo.get("marks_watson"),
        "irene": rinfo.get("holmes_marks")
        or rinfo.get("marks_holmes")
        or rinfo.get("irene_marks"),
        "hunter": rinfo.get("hunter_marks") or rinfo.get("marks_hunter"),
        "moriarty": rinfo.get("moriarty_marks") or rinfo.get("marks_moriarty"),
        "hope": rinfo.get("hope_marks") or rinfo.get("marks_hope"),
    }


def _mark_nonempty(m: Any) -> bool:
    return isinstance(m, dict) and any(v not in (None, "", [], ()) for v in m.values())


def _try_pc_marks(pred: Any, names: tuple[str, ...]) -> Any:
    try:
        import prediction_core as pc  # type: ignore
    except Exception:
        pc = None
    if pc is not None:
        for fn in names:
            if hasattr(pc, fn):
                try:
                    val = getattr(pc, fn)(pred)
                    if _mark_nonempty(val):
                        return val
                except Exception:
                    continue
    try:
        from public_viewer import export_public_snapshot as ex  # type: ignore

        for fn in names:
            if hasattr(ex, fn):
                try:
                    val = getattr(ex, fn)(pred)
                    if _mark_nonempty(val):
                        return val
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _enrich_marks_from_prediction(rinfo: dict[str, Any], logic_marks: dict[str, Any]) -> dict[str, Any]:
    """キャッシュに印が無くても prediction から全ロジック分を必ず生成する。"""
    pred = rinfo.get("prediction")
    if pred is None:
        return logic_marks

    if not _mark_nonempty(logic_marks.get("watson")):
        logic_marks["watson"] = _try_pc_marks(
            pred, ("get_marks_watson", "marks_watson", "watson_marks")
        ) or logic_marks.get("watson")
    if not _mark_nonempty(logic_marks.get("irene")):
        val = None
        try:
            from public_viewer.export_public_snapshot import _irene_marks_for_public  # type: ignore

            val = _irene_marks_for_public(pred)
        except Exception:
            val = _try_pc_marks(
                pred, ("get_marks_irene", "get_irene_marks", "irene_marks", "get_marks_holmes")
            )
        if _mark_nonempty(val):
            logic_marks["irene"] = val
    if not _mark_nonempty(logic_marks.get("hunter")):
        logic_marks["hunter"] = _try_pc_marks(
            pred, ("get_marks_hunter", "get_hunter_marks", "hunter_marks")
        ) or logic_marks.get("hunter")
    if not _mark_nonempty(logic_marks.get("moriarty")):
        logic_marks["moriarty"] = _try_pc_marks(
            pred, ("get_marks_moriarty", "get_moriarty_marks", "moriarty_marks")
        ) or logic_marks.get("moriarty")
    if not _mark_nonempty(logic_marks.get("hope")):
        logic_marks["hope"] = _try_pc_marks(
            pred, ("get_marks_hope", "get_hope_marks", "hope_marks")
        ) or logic_marks.get("hope")
    if not _mark_nonempty(logic_marks.get("baker")):
        logic_marks["baker"] = (
            rinfo.get("baker_marks")
            or rinfo.get("marks_baker")
            or _try_pc_marks(pred, ("get_marks_baker", "get_baker_marks", "baker_marks"))
        )
    return logic_marks


def _public_marks(logic_marks: dict[str, Any]) -> dict[str, str]:
    return {
        "ワ": _format_mark_map(logic_marks.get("watson")),
        "アイ": _format_mark_map(logic_marks.get("irene")),
        "モ": _format_mark_map(logic_marks.get("moriarty")),
        "ハ/ホプ": _format_mark_map(logic_marks.get("hunter") or logic_marks.get("hope")),
        "ベ": _format_mark_map(logic_marks.get("baker")),
    }


def _fmt_dev(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return round(float(v), 1)
    except Exception:
        return None


def _parse_pct_number(v: Any) -> float:
    if v is None or v == "":
        return -1.0
    if isinstance(v, (int, float)):
        x = float(v)
        return x * 100.0 if x <= 1.0 else x
    s = str(v).strip().replace("%", "")
    try:
        return float(s)
    except Exception:
        return -1.0


def _as_holmes_score(v: Any) -> float | None:
    """ホームズ指数として妥当な数値だけ通す。

    Edge の best_score / gate の score=25 など別用途の値はここで弾く。
    公開スナップの実測レンジは概ね 40〜100。
    """
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except Exception:
        return None
    if x != x:  # NaN
        return None
    # 25 は gate 閾値等で全レースに混入しやすい誤値。ホームズ指数としては低すぎる。
    if x < 40.0 or x > 100.0:
        return None
    return x


def _extract_holmes_score(rinfo: dict[str, Any], rid: str | None = None) -> float | None:
    """正式ヘルパー / morning フィールドからホームズ指数を取る。

    禁止:
    - holmes_gate_predict_snap の雑 walk
    - Edge row / rinfo の generic best_score（別指標で 25 になりがち）
    - gate の score / index / holmes
    """
    # 1) 正式: hwm の指数ヘルパー
    if rid:
        try:
            from hwm import _holmes_index_score_and_rank_texts  # type: ignore

            sc, _rank = _holmes_index_score_and_rank_texts(str(rid), rinfo)
            got = _as_holmes_score(sc)
            if got is not None:
                return got
        except Exception:
            pass

    # 2) rinfo 上の明示フィールド（best_score は使わない）
    for key in (
        "morning_holmes_best_score",
        "holmes_index",
        "holmes_score",
        "morning_holmes_index",
    ):
        got = _as_holmes_score(rinfo.get(key))
        if got is not None:
            return got

    # 3) day snap
    try:
        from hwm import _load_day_holmes_score_snap  # type: ignore

        snap = _load_day_holmes_score_snap() or {}
        for bucket in ("morning_scores", "latest_scores", "scores"):
            mp = snap.get(bucket) or {}
            if rid and str(rid) in mp:
                got = _as_holmes_score(mp[str(rid)])
                if got is not None:
                    return got
    except Exception:
        pass

    # 4) gate snap: 明示のホームズ指数キーのみ（score/index 禁止）
    gate = rinfo.get("holmes_gate_predict_snap")
    if isinstance(gate, dict):
        for key in ("holmes_index", "morning_holmes_best_score", "holmes_score"):
            if key in gate:
                got = _as_holmes_score(gate[key])
                if got is not None:
                    return got
    return None


def _fix_pct(v: Any) -> str:
    if v is None or v == "":
        return ""
    try:
        x = float(v)
        if x <= 1.0:
            x *= 100.0
        return f"{x:.3f}%"
    except Exception:
        s = str(v)
        return s if "%" in s else s


def _prediction_by_umaban(pred: Any) -> dict[int, dict[str, Any]]:
    rows = _as_records(pred)
    # also try archive helper
    if not rows:
        try:
            from public_viewer.export_public_snapshot import (  # type: ignore
                _prediction_rows_for_archive,
            )

            rows = _prediction_rows_for_archive(pred) or []
        except Exception:
            rows = []
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        umaban = r.get("馬番") or r.get("umaban") or r.get("number")
        try:
            n = int(umaban)
        except Exception:
            continue
        out[n] = r
    return out


def _build_shutuba(
    rinfo: dict[str, Any], logic_marks: dict[str, Any]
) -> dict[str, Any]:
    df_rows = _as_records(rinfo.get("df"))
    pred_map = _prediction_by_umaban(rinfo.get("prediction"))
    w_map = _marks_umaban_symbol(logic_marks.get("watson"))
    i_map = _marks_umaban_symbol(logic_marks.get("irene"))
    h_map = _marks_umaban_symbol(logic_marks.get("hunter") or logic_marks.get("hope"))

    columns = [
        "枠番",
        "馬番",
        "馬名",
        "騎手",
        "脚質",
        "単勝",
        "人気",
        "斤量",
        "性齢",
        "馬体重",
        "推定勝率",
        "推定3着内率",
        "馬指数",
        "ワトソン",
        "アイリーン",
        "ハンター",
    ]
    mark_columns = ["ワトソン", "アイリーン", "ハンター"]
    rows_out: list[dict[str, Any]] = []

    # prefer df order; else prediction order
    base_rows = df_rows
    if not base_rows:
        base_rows = list(pred_map.values())

    for raw in base_rows:
        umaban_raw = raw.get("馬番") or raw.get("umaban")
        try:
            umaban = int(umaban_raw)
        except Exception:
            continue
        pred = pred_map.get(umaban, {})
        frame_raw = raw.get("枠番") or raw.get("枠") or pred.get("枠番") or 0
        try:
            frame = int(frame_raw)
        except Exception:
            frame = 0
        bg, fg = FRAME_STYLE.get(frame, ("#FFFFFF", "#000000"))
        w_sym = w_map.get(umaban, "")
        i_sym = i_map.get(umaban, "")
        h_sym = h_map.get(umaban, "")
        kyasha = (
            raw.get("脚質")
            or raw.get("推定脚質")
            or pred.get("推定脚質")
            or pred.get("脚質")
            or ""
        )
        win_p = pred.get("prob_win") or pred.get("推定勝率") or raw.get("推定勝率")
        place_p = pred.get("prob_place") or pred.get("推定3着内率") or raw.get("推定3着内率")
        horse_idx = pred.get("馬指数") or raw.get("馬指数") or ""
        row = {
            "枠番": _safe_str(frame or frame_raw),
            "馬番": _safe_str(umaban),
            "馬名": _safe_str(raw.get("馬名") or pred.get("馬名")),
            "騎手": _safe_str(raw.get("騎手") or pred.get("騎手")),
            "脚質": _safe_str(kyasha),
            "単勝": _safe_str(raw.get("単勝") or pred.get("単勝")),
            "人気": _safe_str(raw.get("人気") or pred.get("人気")),
            "斤量": _safe_str(raw.get("斤量") or pred.get("斤量")),
            "性齢": _safe_str(raw.get("性齢") or pred.get("性齢")),
            "馬体重": _safe_str(raw.get("馬体重") or pred.get("馬体重")),
            "推定勝率": _fix_pct(win_p),
            "推定3着内率": _fix_pct(place_p),
            "馬指数": _safe_str(horse_idx),
            "ワトソン": w_sym,
            "アイリーン": i_sym,
            "ハンター": h_sym,
            "_style": {
                "frame": frame,
                "frame_bg": bg,
                "frame_fg": fg,
                "cancel": bool(raw.get("取消") or raw.get("cancel")),
                "honmei": {
                    "ワトソン": w_sym == "◎",
                    "アイリーン": i_sym == "◎",
                    "ハンター": h_sym == "◎",
                },
            },
        }
        rows_out.append(row)

    # UI デフォルトは「推定3着内率の高い順」（app.js は default 時に snapshot 順を維持）
    rows_out.sort(
        key=lambda r: (
            -_parse_pct_number(r.get("推定3着内率")),
            int(r["馬番"]) if str(r.get("馬番")).isdigit() else 99,
        )
    )
    return {
        "columns": columns,
        "mark_columns": mark_columns,
        "rows": rows_out,
        "predicted": bool(rows_out) and bool(pred_map or any(logic_marks.values())),
    }


def _pick_best_logic(logic_marks: dict[str, Any], rinfo: dict[str, Any]) -> tuple[str, str]:
    aliases = {
        "ワトソン": "watson",
        "ワトソンロジック": "watson",
        "watson": "watson",
        "アイリーン": "irene",
        "irene": "irene",
        "ハンター": "hunter",
        "hunter": "hunter",
        "ハ/ホプ": "hunter",
        "ホプキンス": "hunter",
        "hope": "hunter",
        "モリア": "moriarty",
        "モリアーティ": "moriarty",
        "moriarty": "moriarty",
    }
    hm = rinfo.get("hunter_mode")
    hl = rinfo.get("hunter_label")
    if hm in (True, 1, "1", "true", "True") or (isinstance(hl, str) and "ハンター" in hl):
        return "hunter", LOGIC_LABELS["hunter"]

    explicit = rinfo.get("best_logic") or rinfo.get("sui") or rinfo.get("recommended_logic") or hl
    if explicit:
        key = aliases.get(str(explicit).strip(), str(explicit).strip().lower())
        if key in LOGIC_LABELS:
            return key, LOGIC_LABELS[key]
        return key, str(explicit)
    for key in ("hunter", "irene", "watson", "moriarty"):
        if _mark_nonempty(logic_marks.get(key)):
            return key, LOGIC_LABELS.get(key, key)
    return "hunter", LOGIC_LABELS["hunter"]


def _cells_for(best_key: str, logic_marks: dict[str, Any], rinfo: dict[str, Any]) -> dict[str, str]:
    existing = rinfo.get("cells") or rinfo.get("logic_cells")
    if isinstance(existing, dict) and existing:
        # normalize keys
        return {
            "ワ": _safe_str(existing.get("ワ") or existing.get("ワトソン") or "-") or "-",
            "アイ": _safe_str(existing.get("アイ") or existing.get("アイリーン") or "-") or "-",
            "モ": _safe_str(existing.get("モ") or existing.get("モリアーティ") or "-") or "-",
            "ハ/ホプ": _safe_str(existing.get("ハ/ホプ") or existing.get("ハンター") or "-") or "-",
            "ベ": _safe_str(existing.get("ベ") or "-") or "-",
        }
    cells = {"ワ": "-", "アイ": "-", "モ": "-", "ハ/ホプ": "-", "ベ": "-"}
    if _format_mark_map(logic_marks.get("watson")) != "-":
        cells["ワ"] = "様子・中位帯"
    if _format_mark_map(logic_marks.get("irene")) != "-":
        cells["アイ"] = "様子・様子見"
    hl = rinfo.get("hunter_label")
    if isinstance(hl, str) and hl.strip():
        cells["ハ/ホプ"] = "ハンター"
    elif _format_mark_map(logic_marks.get("hunter") or logic_marks.get("hope")) != "-":
        cells["ハ/ホプ"] = "ハンター"
    elif best_key == "hunter":
        cells["ハ/ホプ"] = "ハンター"
    if best_key == "watson" and cells["ワ"] == "-":
        cells["ワ"] = "様子・中位帯"
    if best_key == "irene" and cells["アイ"] == "-":
        cells["アイ"] = "様子・様子見"
    if best_key == "moriarty":
        cells["モ"] = "モリアーティ"
    return cells


def _race_to_public(rid: str, rinfo: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(rinfo, dict):
        return None
    info = _info(rinfo)
    logic_marks = _enrich_marks_from_prediction(rinfo, _get_logic_marks(rinfo))
    shutuba = _build_shutuba(rinfo, logic_marks)
    if not shutuba.get("rows"):
        return None
    best_key, best_label = _pick_best_logic(logic_marks, rinfo)
    cells = _cells_for(best_key, logic_marks, rinfo)
    marks = _public_marks(logic_marks)
    # if already public marks on rinfo
    if isinstance(rinfo.get("marks"), dict) and any(
        isinstance(v, str) and v not in ("", "-") for v in rinfo["marks"].values()
    ):
        src = rinfo["marks"]
        marks = {
            "ワ": _safe_str(src.get("ワ") or marks["ワ"]) or "-",
            "アイ": _safe_str(src.get("アイ") or marks["アイ"]) or "-",
            "モ": _safe_str(src.get("モ") or marks["モ"]) or "-",
            "ハ/ホプ": _safe_str(src.get("ハ/ホプ") or marks["ハ/ホプ"]) or "-",
            "ベ": _safe_str(src.get("ベ") or "-") or "-",
        }

    predicted_at = rinfo.get("predicted_at")
    if isinstance(predicted_at, (int, float)):
        try:
            predicted_at = datetime.fromtimestamp(float(predicted_at), tz=_JST).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            predicted_at = str(predicted_at)
    elif predicted_at is not None:
        predicted_at = str(predicted_at)

    place = _safe_str(info.get("place") or rinfo.get("place"))
    r_no = _safe_str(info.get("R") or rinfo.get("R"))
    name = _safe_str(info.get("name") or rinfo.get("race_name") or rinfo.get("name"))
    start = _safe_str(info.get("start_time") or rinfo.get("start_time"))

    score = _extract_holmes_score(rinfo, rid)
    if score is None:
        holmes = ""
    else:
        holmes = str(int(round(score))) if abs(score - round(score)) < 1e-6 else f"{score:.1f}".rstrip("0").rstrip(".")

    return {
        "race_id": _safe_str(rid),
        "place": place,
        "R": r_no,
        "name": name,
        "start_time": start,
        "weather": _safe_str(info.get("weather") or info.get("天候") or rinfo.get("weather")),
        "baba": _safe_str(info.get("baba") or info.get("馬場") or rinfo.get("baba")),
        "dev": _fmt_dev(rinfo.get("dev")),
        "rank": rinfo.get("rank"),
        "holmes_index": holmes,
        "morning_holmes_index": holmes or None,
        "best_logic": best_key,
        "best_logic_label": best_label,
        "cells": cells,
        "marks": marks,
        "predicted": True,
        "predicted_at": predicted_at,
        "pdf_url": _safe_str(rinfo.get("supabase_pdf_url") or rinfo.get("pdf_url")),
        "help_pdf_url": _safe_str(
            rinfo.get("supabase_help_pdf_url") or rinfo.get("help_pdf_url")
        ),
        "grade": rinfo.get("grade"),
        "shutuba": shutuba,
    }


def _apply_holmes_ranks(races: list[dict[str, Any]]) -> None:
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in races:
        try:
            scored.append((float(r.get("holmes_index") or 0), r))
        except Exception:
            scored.append((0.0, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    n = len(scored)
    for i, (_score, r) in enumerate(scored, start=1):
        r["holmes_index_rank"] = i
        r["holmes_rank_text"] = f"{i}位/{n}レース中"
        # matrix display sometimes embeds rank in holmes_index string — keep numeric separate


def _matrix_row(r: dict[str, Any]) -> dict[str, Any]:
    hi = _safe_str(r.get("holmes_index"))
    rank_txt = _safe_str(r.get("holmes_rank_text"))
    holmes_disp = f"{hi}（{rank_txt}）" if hi and rank_txt else hi
    cells = r.get("cells") or {}
    best = r.get("best_logic")
    sui = {
        "watson": "ワトソン",
        "irene": "アイリーン",
        "hunter": "ハンター",
        "moriarty": "モリアーティ",
    }.get(str(best), _safe_str(r.get("best_logic_label")) or "-")
    return {
        "race_id": r.get("race_id"),
        "race": f"{r.get('place')} {r.get('R')}R {r.get('name')}".strip(),
        "dev": ("" if r.get("dev") is None else f"{float(r.get('dev')):.1f}"),
        "sui": sui,
        "holmes_index": holmes_disp,
        "ワトソン": cells.get("ワ", "-"),
        "アイリーン": cells.get("アイ", "-"),
        "ワ": cells.get("ワ", "-"),
        "アイ": cells.get("アイ", "-"),
        "第3探偵": cells.get("ハ/ホプ", "-") if cells.get("ハ/ホプ") not in ("-", "") else cells.get("モ", "-"),
    }


def _top5(races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        races,
        key=lambda r: (
            -float(r.get("holmes_index") or 0) if str(r.get("holmes_index") or "").replace(".", "", 1).isdigit() else 0,
            int(r.get("holmes_index_rank") or 999),
        ),
    )
    out = []
    for i, r in enumerate(ordered[:5], start=1):
        out.append(
            {
                "n": i,
                "race_id": r.get("race_id"),
                "line": (
                    f"{r.get('place')} {r.get('R')}R / "
                    f"{r.get('best_logic_label') or r.get('best_logic')} / "
                    f"ホームズ指数 {r.get('holmes_index')}（{r.get('holmes_rank_text')}）"
                ),
                "holmes_index": _safe_str(r.get("holmes_index")),
                "holmes_rank_text": r.get("holmes_rank_text"),
                "holmes_index_rank": r.get("holmes_index_rank"),
                "best_logic_label": r.get("best_logic_label"),
                "place": r.get("place"),
                "R": r.get("R"),
            }
        )
    return out


def build_snapshot(races_cache: dict[str, Any], day: str) -> dict[str, Any]:
    morning_map: dict[str, Any] = {}
    try:
        from public_viewer.export_public_snapshot import _morning_holmes_score_map  # type: ignore

        morning_map = dict(_morning_holmes_score_map(races_cache) or {})
    except Exception:
        morning_map = {}
    try:
        from hwm import _load_day_holmes_score_snap  # type: ignore

        snap = _load_day_holmes_score_snap() or {}
        for bucket in ("morning_scores", "latest_scores", "scores"):
            for k, v in (snap.get(bucket) or {}).items():
                ks = str(k)
                if ks in morning_map:
                    continue
                try:
                    morning_map[ks] = float(v)
                except Exception:
                    pass
    except Exception:
        pass

    public_races: list[dict[str, Any]] = []
    skipped = 0
    for rid in sorted(races_cache.keys(), key=str):
        rinfo = races_cache[rid]
        if isinstance(rinfo, dict) and rid in morning_map and rinfo.get("holmes_index") in (None, ""):
            got = _as_holmes_score(morning_map[rid])
            if got is not None:
                rinfo = dict(rinfo)
                rinfo["holmes_index"] = got
        pub = _race_to_public(str(rid), rinfo)
        if pub is None:
            skipped += 1
            continue
        if rid in morning_map and not pub.get("holmes_index"):
            got = _as_holmes_score(morning_map[rid])
            if got is not None:
                pub["holmes_index"] = str(int(round(got)))
                pub["morning_holmes_index"] = pub["holmes_index"]
        public_races.append(pub)
    _apply_holmes_ranks(public_races)

    by_place: dict[str, list[dict[str, Any]]] = {}
    for r in public_races:
        by_place.setdefault(r.get("place") or "?", []).append(r)

    # stable venue order by first race id
    venue_order = sorted(
        by_place.keys(),
        key=lambda p: min((x.get("race_id") or "") for x in by_place[p]),
    )
    venues = []
    for place in venue_order:
        rs = sorted(
            by_place[place],
            key=lambda r: int(r["R"]) if str(r.get("R") or "").isdigit() else 99,
        )
        venues.append(
            {
                "place": place,
                "matrix": [_matrix_row(r) for r in rs],
                "races": rs,
            }
        )

    now = datetime.now(_JST).strftime("%Y-%m-%dT%H:%M:%S")
    mode = "15"
    pre_line = "・発走15分前前後（全レース）"
    timing = (
        "【主な更新タイミング】\n"
        "・開催日早朝6時頃（全レース一斉）\n"
        "・発走1時間前頃（重賞のみ）\n"
        f"{pre_line}\n"
        "※更新されない場合は通信障害など運用上のトラブルが発生しております。ご容赦ください"
    )
    return {
        "schema_version": 3,
        "updated_at": now,
        "schedule_date": day,
        "top5": _top5(public_races),
        "venues": venues,
        "race_count": len(public_races),
        "venue_count": len(venues),
        "pre_race_trigger_mode": mode,
        "update_timing_pre_race_line": pre_line,
        "update_timing_text": timing,
        "cleared": False,
        "_build_via": "standalone_publish_from_cache",
        "_skipped_races": skipped,
    }


def _upload_diag(payload: dict[str, Any]) -> None:
    try:
        from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

        upload_json_object("ops/standalone_publish_last.json", payload)
        # also dump build_public_snapshot source for next fix
        try:
            import inspect
            from public_viewer.export_public_snapshot import build_public_snapshot  # type: ignore

            upload_json_object(
                "ops/build_public_snapshot_source.py.json",
                {
                    "updated_at": datetime.now(_JST).isoformat(timespec="seconds"),
                    "source": inspect.getsource(build_public_snapshot)[:120000],
                },
            )
        except Exception:
            pass
    except Exception:
        pass


def run() -> dict[str, Any]:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    _load_env(root)

    day, races, notes = _load_races(root)
    if not races:
        out = {"ok": False, "error": "empty_races_cache", "notes": notes, "schedule_date": day}
        _upload_diag(out)
        return out

    # sample diag
    rid0 = sorted(races.keys(), key=str)[0]
    r0 = races[rid0]
    sample = {
        "id": rid0,
        "keys": sorted(str(k) for k in r0.keys()) if isinstance(r0, dict) else type(r0).__name__,
        "info_keys": sorted(str(k) for k in _info(r0).keys()) if isinstance(r0, dict) else [],
        "has_df": isinstance(r0, dict) and r0.get("df") is not None,
        "has_prediction": isinstance(r0, dict) and r0.get("prediction") is not None,
        "holmes_gate_type": type(r0.get("holmes_gate_predict_snap")).__name__ if isinstance(r0, dict) else None,
        "extracted_holmes": _extract_holmes_score(r0, rid0) if isinstance(r0, dict) else None,
        "dev_fmt": _fmt_dev(r0.get("dev")) if isinstance(r0, dict) else None,
    }
    notes.append(f"sample={json.dumps(sample, ensure_ascii=False, default=str)[:800]}")

    snap = build_snapshot(races, day)
    if int(snap.get("race_count") or 0) <= 0:
        out = {
            "ok": False,
            "error": "standalone_built_empty",
            "notes": notes,
            "n_races_cache": len(races),
            "skipped": snap.get("_skipped_races"),
        }
        _upload_diag(out)
        return out

    from public_viewer.export_public_snapshot import upload_json_object  # type: ignore

    # strip private keys before upload
    skipped = snap.pop("_skipped_races", None)
    via = snap.pop("_build_via", None)
    url, err = upload_json_object("snapshots/latest.json", snap)
    out = {
        "ok": not err,
        "error": err,
        "url": url,
        "via": via,
        "schedule_date": day,
        "race_count": snap.get("race_count"),
        "venue_count": snap.get("venue_count"),
        "updated_at": snap.get("updated_at"),
        "n_races_cache": len(races),
        "skipped": skipped,
        "notes": notes,
    }
    _upload_diag(out)
    return out


def main() -> int:
    try:
        out = run()
    except Exception as e:
        out = {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()[-3000:],
        }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

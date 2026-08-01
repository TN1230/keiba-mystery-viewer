#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""レース予想ペース（短いラベル）の抽出・算出と snapshot 埋め込み。

PDF と同じく estimate_race_pace_with_reason を使い、閲覧要約向けに
「やや遅」「中」「やや速」等の短表記だけを公開する。
"""

from __future__ import annotations

import re
from typing import Any

# PDF 実測で見えた表記＋一般的な拡張
_KNOWN = (
    "超ハイ",
    "ハイ",
    "やや速",
    "中",
    "やや遅",
    "スロー",
    "超スロー",
)


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def normalize_pace_label(raw: Any) -> str:
    """短いペースラベルに正規化。不明は空。"""
    s = _safe_str(raw)
    if not s:
        return ""
    s = s.replace("ペース", "").replace("予想", "").strip(" :：/-")
    # 括弧付き理由が混ざっていたら除去
    s = re.split(r"[（(]", s, maxsplit=1)[0].strip()
    if not s or len(s) > 12:
        return ""
    for lab in _KNOWN:
        if s == lab or s.startswith(lab):
            return lab
    # 既知以外でも短い日本語ラベルなら通す（本体側の表記揺れ吸収）
    if re.fullmatch(r"[一-龥ぁ-んァ-ンー]+", s) and 1 <= len(s) <= 6:
        return s
    return ""


def _from_stored_fields(info: dict[str, Any], rinfo: dict[str, Any]) -> str:
    for src in (rinfo, info):
        if not isinstance(src, dict):
            continue
        for key in (
            "pace_label",
            "予想ペース",
            "pace",
            "race_pace",
            "pace_est",
            "predicted_pace",
        ):
            lab = normalize_pace_label(src.get(key))
            if lab:
                return lab
        # nested
        for nest_key in ("pace_est", "pace_info", "meta"):
            nest = src.get(nest_key)
            if isinstance(nest, dict):
                for key in ("pace_label", "label", "pace", "予想ペース"):
                    lab = normalize_pace_label(nest.get(key))
                    if lab:
                        return lab
    return ""


def _compute_via_server(rinfo: dict[str, Any]) -> str:
    """サーバー上の PDF と同じ推定関数を呼ぶ。失敗時は空。"""
    df_src = rinfo.get("df")
    pred = rinfo.get("prediction")
    try:
        import hwm  # type: ignore

        shutuba_fn = getattr(hwm, "_shutsuba_for_pace", None)
        est_fn = getattr(hwm, "estimate_race_pace_with_reason", None)
        if not callable(est_fn):
            # 別名の置き場
            for mod_name in ("pace_utils", "race_pace", "yokuumakun_pace"):
                try:
                    mod = __import__(mod_name)
                except Exception:
                    continue
                est_fn = getattr(mod, "estimate_race_pace_with_reason", None)
                shutuba_fn = getattr(mod, "_shutsuba_for_pace", shutuba_fn)
                if callable(est_fn):
                    break
        if not callable(est_fn):
            return ""
        pace_df = None
        if callable(shutuba_fn):
            try:
                pace_df = shutuba_fn(df_src, pred)
            except Exception:
                pace_df = None
        if pace_df is None:
            pace_df = pred if pred is not None else df_src
        out = est_fn(pace_df)
        if isinstance(out, (tuple, list)) and out:
            return normalize_pace_label(out[0])
        return normalize_pace_label(out)
    except Exception:
        return ""


def extract_pace_fields(
    info: dict[str, Any] | None = None,
    rinfo: dict[str, Any] | None = None,
) -> dict[str, str]:
    info = info if isinstance(info, dict) else {}
    rinfo = rinfo if isinstance(rinfo, dict) else {}
    label = _from_stored_fields(info, rinfo)
    if not label:
        label = _compute_via_server(rinfo)
    return {
        "pace_label": label,
        "pace_display": f"予想ペース: {label}" if label else "",
    }


def enrich_snapshot_with_pace_label(
    snap: dict[str, Any], races_cache: dict[str, Any]
) -> int:
    """公開 snap の各 race に pace_label を埋める。更新件数を返す。"""
    if not isinstance(snap, dict) or not isinstance(races_cache, dict):
        return 0
    n = 0
    for venue in snap.get("venues") or []:
        if not isinstance(venue, dict):
            continue
        for race in venue.get("races") or []:
            if not isinstance(race, dict):
                continue
            rid = str(race.get("race_id") or "")
            rinfo = races_cache.get(rid) if rid else None
            if not isinstance(rinfo, dict):
                fields = extract_pace_fields(race, None)
            else:
                info = rinfo.get("info") if isinstance(rinfo.get("info"), dict) else {}
                fields = extract_pace_fields(info, rinfo)
            lab = fields.get("pace_label") or ""
            if not lab:
                continue
            if race.get("pace_label") != lab:
                race["pace_label"] = lab
                race["pace_display"] = fields.get("pace_display") or f"予想ペース: {lab}"
                n += 1
    return n

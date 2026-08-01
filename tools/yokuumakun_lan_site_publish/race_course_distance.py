#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""レース条件（芝/ダート/障害 + 距離）の正規化と snapshot 埋め込み。

キャッシュ info には course / distance / course_division があるが、
公開 latest.json の race オブジェクトへ載っていないことがある。
"""

from __future__ import annotations

import re
from typing import Any


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def normalize_surface(raw: Any) -> str:
    """芝 / ダート / 障害 に正規化。不明は空文字。"""
    s = _safe_str(raw)
    if not s:
        return ""
    # よくある結合表記「ダート1000」「芝・左」など
    if "障害" in s or s.startswith("障"):
        return "障害"
    if "ダート" in s or s.startswith("ダ") or "dirt" in s.lower():
        return "ダート"
    if "芝" in s or "turf" in s.lower():
        return "芝"
    return ""


def normalize_distance_m(raw: Any) -> str:
    """距離をメートル数値文字列に（単位なし）。不明は空。"""
    if raw is None or raw == "":
        return ""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        n = int(round(float(raw)))
        return str(n) if n > 0 else ""
    s = _safe_str(raw)
    if not s:
        return ""
    m = re.search(r"(\d{3,4})\s*m?", s, flags=re.I)
    if not m:
        return ""
    try:
        n = int(m.group(1))
    except Exception:
        return ""
    return str(n) if n > 0 else ""


def normalize_course_division(raw: Any) -> str:
    """右 / 左 / 直線 など。余計な括弧は外す。

    「不明」など意味のない区分は空にして、要約のノイズにしない。
    """
    s = _safe_str(raw)
    if not s:
        return ""
    s = s.strip("()（）[]【】 ")
    low = s.lower()
    if s in ("不明", "未知", "なし", "-", "—", "－", "?", "？") or low in (
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
    ):
        return ""
    # 「右回り」→「右」
    for token in ("直線", "右", "左"):
        if token in s:
            return token
    # 右/左/直線以外の短い区分は採用しない（不明系の表記揺れを落とす）
    return ""


def format_course_label(
    *,
    course: Any = "",
    distance: Any = "",
    course_division: Any = "",
) -> str:
    """表示用: ダート1000m（右） / 芝1600m / 障害2770m"""
    surface = normalize_surface(course)
    dist = normalize_distance_m(distance)
    # course に距離が埋まっている場合の保険
    if not dist:
        dist = normalize_distance_m(course)
    if not surface:
        # 「ダ1000m」のような course のみ
        surface = normalize_surface(course)
    div = normalize_course_division(course_division)

    if not surface and not dist:
        return ""
    if surface and dist:
        label = f"{surface}{dist}m"
    elif surface:
        label = surface
    else:
        label = f"{dist}m"
    # 右/左/直線だけ括弧付きで付ける（不明は付けない）
    if div in ("右", "左", "直線") and div not in label:
        label = f"{label}（{div}）"
    return label


def extract_course_distance_fields(
    info: dict[str, Any] | None = None,
    rinfo: dict[str, Any] | None = None,
) -> dict[str, str]:
    info = info if isinstance(info, dict) else {}
    rinfo = rinfo if isinstance(rinfo, dict) else {}
    course = (
        info.get("course")
        or info.get("コース")
        or info.get("surface")
        or rinfo.get("course")
        or ""
    )
    distance = (
        info.get("distance")
        or info.get("距離")
        or info.get("kyori")
        or rinfo.get("distance")
        or ""
    )
    division = (
        info.get("course_division")
        or info.get("回り")
        or info.get("コース区分")
        or rinfo.get("course_division")
        or ""
    )
    surface = normalize_surface(course)
    dist = normalize_distance_m(distance) or normalize_distance_m(course)
    div = normalize_course_division(division)
    label = format_course_label(course=course or surface, distance=dist, course_division=div)
    return {
        "course": surface,
        "distance": dist,
        "course_division": div,
        "course_label": label,
    }


def enrich_snapshot_with_course_distance(
    snap: dict[str, Any], races_cache: dict[str, Any]
) -> int:
    """公開 snap の各 race に course/distance/course_label を埋める。更新件数を返す。"""
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
                # 既存フィールドだけでラベル生成を試す
                fields = extract_course_distance_fields(race, None)
            else:
                info = rinfo.get("info") if isinstance(rinfo.get("info"), dict) else {}
                fields = extract_course_distance_fields(info, rinfo)
            if not fields.get("course_label") and not fields.get("course") and not fields.get("distance"):
                continue
            changed = False
            for k, v in fields.items():
                if v and race.get(k) != v:
                    race[k] = v
                    changed = True
            if changed:
                n += 1
    return n

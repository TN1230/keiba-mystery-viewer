#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一斉予想（morning_bulk）の DISCORD_WEBHOOK_TEST_ALWAYS 送信フィルタ。

テスト webhook へは開始・エラー・終了のみ送る。
本番 webhook（DISCORD_WEBHOOK_URL_*）の挙動は変えない。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

# 明示 allow（開始 / 終了 / 致命エラー / 管理画面からの開始）
_EXACT_ALLOW = frozenset(
    {
        "morning_bulk_worker_start",
        "morning_bulk_worker_done",
        "morning_bulk_worker_fatal",
        "morning_bulk_spawn",
        "admin_morning_bulk_rerun",
        "morning_bulk_odds_suspicion_modem_reboot",
    }
)

_ERROR_STATUSES = frozenset(
    {"error", "fatal", "fail", "failed", "crit", "critical"}
)

_MARKER = "morning_bulk_test_webhook_filter"


def is_morning_bulk_ops_event(event: str) -> bool:
    ev = (event or "").strip()
    if not ev:
        return False
    if ev.startswith("morning_bulk"):
        return True
    if ev == "admin_morning_bulk_rerun":
        return True
    return False


def allow_morning_bulk_test_always(event: str, status: str = "") -> bool:
    """TEST_ALWAYS ミラーへ morning_bulk 系を送ってよいか。"""
    ev = (event or "").strip()
    st = (status or "").strip().lower()
    if not is_morning_bulk_ops_event(ev):
        return True
    if ev in _EXACT_ALLOW:
        return True
    if ev.startswith("morning_bulk_quality"):
        return True
    if st in _ERROR_STATUSES:
        return True
    return False


def _env_keys_to_clear() -> tuple[str, ...]:
    return (
        "DISCORD_WEBHOOK_TEST_ALWAYS",
        "HWM_DISCORD_WEBHOOK_TEST_ALWAYS",
    )


def _module_attrs_to_clear(mod) -> list[str]:
    """モジュール上にキャッシュされた TEST_ALWAYS URL らしき属性名を列挙。"""
    keys = []
    for name in dir(mod):
        low = name.lower()
        if "test_always" in low or "always_mirror" in low:
            keys.append(name)
            continue
        if "webhook" in low and "test" in low and "always" in low:
            keys.append(name)
    return keys


@contextmanager
def suppress_test_always_env_and_module(mod=None) -> Iterator[None]:
    """TEST_ALWAYS 向け env / モジュールキャッシュを一時的に外す。"""
    saved_env: dict[str, str] = {}
    urls: set[str] = set()
    for key in _env_keys_to_clear():
        if key in os.environ:
            saved_env[key] = os.environ.pop(key)
            if saved_env[key].strip():
                urls.add(saved_env[key].strip())

    saved_attrs: dict[str, object] = {}
    if mod is not None:
        names = set(_module_attrs_to_clear(mod))
        # env と同じ URL 文字列を持つ属性もキャッシュ扱いで外す
        for name in dir(mod):
            if name.startswith("__"):
                continue
            try:
                val = getattr(mod, name)
            except Exception:
                continue
            if isinstance(val, str) and val.strip() in urls:
                names.add(name)
            elif isinstance(val, (list, tuple, set)):
                try:
                    if any(isinstance(x, str) and x.strip() in urls for x in val):
                        names.add(name)
                except Exception:
                    pass
        for name in names:
            if hasattr(mod, name):
                saved_attrs[name] = getattr(mod, name)
                replacement: object = None
                cur = saved_attrs[name]
                if isinstance(cur, str):
                    replacement = ""
                elif isinstance(cur, list):
                    replacement = [x for x in cur if not (isinstance(x, str) and x.strip() in urls)]
                elif isinstance(cur, tuple):
                    replacement = tuple(
                        x for x in cur if not (isinstance(x, str) and x.strip() in urls)
                    )
                elif isinstance(cur, set):
                    replacement = {x for x in cur if not (isinstance(x, str) and x.strip() in urls)}
                try:
                    setattr(mod, name, replacement)
                except Exception:
                    pass
    try:
        yield
    finally:
        for key, val in saved_env.items():
            os.environ[key] = val
        if mod is not None:
            for name, val in saved_attrs.items():
                try:
                    setattr(mod, name, val)
                except Exception:
                    pass


def wrap_notify_action(orig_notify_action, mod=None):
    """notify_action をラップし、morning_bulk の中間ログを TEST_ALWAYS から除外。"""

    def notify_action(event, status="ok", detail="", **kwargs):
        if is_morning_bulk_ops_event(str(event)) and not allow_morning_bulk_test_always(
            str(event), str(status)
        ):
            with suppress_test_always_env_and_module(mod):
                return orig_notify_action(event, status=status, detail=detail, **kwargs)
        return orig_notify_action(event, status=status, detail=detail, **kwargs)

    notify_action.__wrapped__ = orig_notify_action  # type: ignore[attr-defined]
    setattr(notify_action, _MARKER, True)
    return notify_action


def apply_to_ops_module(mod) -> bool:
    """ops_discord_notify モジュールにフィルタを適用。既に適用済みなら False。"""
    fn = getattr(mod, "notify_action", None)
    if fn is None:
        raise RuntimeError("ops_discord_notify.notify_action not found")
    if getattr(fn, _MARKER, False):
        return False
    mod.notify_action = wrap_notify_action(fn, mod=mod)
    return True

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""メイン機 yokuumakun から race_progression_sim 関連を auto-x へコピーする。"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import sys
from pathlib import Path

SIM_ENTRY = "race_progression_sim.py"

# エントリから辿るとき、標準庫っぽい名前はスキップ
_SKIP_MODS = {
    "streamlit",
    "pandas",
    "numpy",
    "requests",
    "sklearn",
    "torch",
    "PIL",
    "cv2",
    "matplotlib",
    "seaborn",
    "plotly",
    "bs4",
    "lxml",
    "dotenv",
    "yaml",
    "tqdm",
    "joblib",
    "scipy",
}


def default_source_candidates() -> list[Path]:
    cands: list[Path] = []
    env_src = (os.environ.get("YOKUMAKUN_SIM_SOURCE") or "").strip()
    if env_src:
        cands.append(Path(env_src))
    marker = Path(__file__).resolve().parent / ".sim_source"
    if marker.is_file():
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            cands.append(Path(text))
    cands.extend(
        [
            Path(r"C:\Users\mocco\Desktop\yokuumakun"),
            Path.home() / "Desktop" / "yokuumakun",
            Path("/home/tn/yokuumakun"),
            Path("/home/tn/Desktop/yokuumakun"),
            Path("/home/tn/デスクトップ/yokuumakun"),
            Path("/opt/yokuumakun"),
            Path("/opt/yokuumakun_auto"),
            Path("/opt/yokuumakun_auto-r"),
            Path("/opt/yokuumakun_auto-x"),  # 既にコピー済みの場合
        ]
    )
    # サーバー上の広めの探索（浅い）
    for base in (Path("/home/tn"), Path("/opt"), Path.home()):
        if not base.is_dir():
            continue
        try:
            for p in base.iterdir():
                if p.is_dir() and (p / SIM_ENTRY).is_file():
                    cands.append(p)
        except Exception:
            pass
    return cands


def resolve_source(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not (p / SIM_ENTRY).is_file():
            raise SystemExit(f"source missing {SIM_ENTRY}: {p}")
        return p
    for c in default_source_candidates():
        try:
            p = c.expanduser().resolve()
        except Exception:
            continue
        if (p / SIM_ENTRY).is_file():
            return p
    raise SystemExit(
        f"{SIM_ENTRY} が見つかりません。YOKUMAKUN_SIM_SOURCE か --source でメイン機 yokuumakun を指定してください。"
    )


def _local_imports(py: Path) -> set[str]:
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"), filename=str(py))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:
                names.add(node.module.split(".")[0])
            elif node.module:
                names.add(node.module.split(".")[0])
    return {n for n in names if n and n not in _SKIP_MODS and not n.startswith("_")}


def collect_files(src: Path) -> list[Path]:
    entry = src / SIM_ENTRY
    files = {entry}
    # エントリのローカル import を同梱
    for mod in _local_imports(entry):
        for cand in (src / f"{mod}.py", src / mod / "__init__.py"):
            if cand.is_file():
                files.add(cand if cand.name != "__init__.py" else cand.parent)
                break
    # よくある同居アセット（あれば）
    for pat in (
        "tenkai*.py",
        "*progression*.py",
        "*tenkai*.html",
        "*progression*.html",
        "tenkai_assets/**/*",
    ):
        for p in src.glob(pat):
            if p.is_file():
                files.add(p)
    return sorted(files, key=lambda p: str(p))


def copy_tree_item(src_item: Path, src_root: Path, dst_root: Path) -> list[str]:
    rel = src_item.relative_to(src_root)
    dst = dst_root / rel
    out: list[str] = []
    if src_item.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src_item, dst)
        out.append(f"dir {rel}")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_item, dst)
        out.append(f"file {rel}")
    return out


def copy_sim(source: Path, dest: Path, force: bool = False) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    dest_entry = dest / SIM_ENTRY
    existed = dest_entry.is_file()
    if existed and not force:
        # 既にある場合でもソースより古い/小さいなら上書き推奨だが、既定はスキップしない（force で明示）
        pass
    copied: list[str] = []
    for item in collect_files(source):
        copied.extend(copy_tree_item(item, source, dest))
    help_txt = ""
    try:
        import subprocess

        py = dest / ".venv" / "bin" / "python"
        exe = str(py) if py.is_file() else sys.executable
        cp = subprocess.run(
            [exe, str(dest / SIM_ENTRY), "--help"],
            cwd=str(dest),
            capture_output=True,
            text=True,
            timeout=60,
        )
        help_txt = (cp.stdout or "") + (cp.stderr or "")
    except Exception as e:
        help_txt = f"(help failed: {type(e).__name__}: {e})"
    flags = sorted(set(re.findall(r"--[a-zA-Z0-9][a-zA-Z0-9\-]*", help_txt)))
    return {
        "ok": (dest / SIM_ENTRY).is_file(),
        "source": str(source),
        "dest": str(dest),
        "existed_before": existed,
        "copied": copied,
        "cli_flags": flags,
        "help_excerpt": help_txt[:1500],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="")
    ap.add_argument("--dest", default="/opt/yokuumakun_auto-x")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    src = resolve_source(args.source or None)
    result = copy_sim(src, Path(args.dest), force=bool(args.force))
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

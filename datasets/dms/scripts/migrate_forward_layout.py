#!/usr/bin/env python3
"""将 isa / isa_class 目录迁入 forward/detect、forward/classify（默认符号链接，保留原数据）。"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def link_or_move(src: Path, dst: Path, *, move: bool) -> None:
    if not src.is_dir():
        print(f"  skip（不存在）: {src}")
        return
    if dst.exists():
        print(f"  已存在: {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(src), str(dst))
        print(f"  moved {src} -> {dst}")
    else:
        dst.symlink_to(src.resolve())
        print(f"  symlink {dst} -> {src.resolve()}")


def migrate_pack(pack_dir: Path, *, move: bool) -> None:
    forward = pack_dir / "forward"
    forward.mkdir(parents=True, exist_ok=True)
    link_or_move(pack_dir / "isa", forward / "detect", move=move)
    link_or_move(pack_dir / "isa_class", forward / "classify", move=move)


def migrate_inbox(dms_root: Path, *, move: bool) -> None:
    for old, new in (
        ("isa", "forward/detect"),
        ("isa_class", "forward/classify"),
    ):
        src = dms_root / "inbox" / old
        dst = dms_root / "inbox" / new
        if src.is_dir():
            link_or_move(src, dst, move=move)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pack-dir", type=Path, required=True, help="如 .../packs/dms_v1")
    p.add_argument("--dms-root", type=Path, help="datasets/dms 根，迁移 inbox")
    p.add_argument("--move", action="store_true", help="移动而非符号链接")
    args = p.parse_args()
    migrate_pack(args.pack_dir.resolve(), move=args.move)
    if args.dms_root:
        migrate_inbox(args.dms_root.resolve(), move=args.move)
    print("完成。请运行 refresh_yaml.py 并刷新平台 catalog。")


if __name__ == "__main__":
    main()

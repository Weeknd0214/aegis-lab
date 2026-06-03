#!/usr/bin/env python3
"""将 dam / dam_0417 合并为 dam/batch_0516、dam/batch_0417（默认符号链接）。"""
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
    dam_root = pack_dir / "dam"
    dam_0417 = pack_dir / "dam_0417"
    batch_0516 = dam_root / "batch_0516"
    batch_0417 = dam_root / "batch_0417"

    if batch_0516.exists() and batch_0417.exists():
        print("  dam 已迁移，跳过")
        return

    # 当前 dam 为扁平 YOLO 布局（images/labels 在根下）
    if dam_root.is_dir() and (dam_root / "images").is_dir() and not batch_0516.exists():
        stash = pack_dir / "_dam_stash_0516"
        if stash.exists():
            print(f"  清理旧 stash: {stash}")
            if stash.is_symlink():
                stash.unlink()
            else:
                shutil.rmtree(stash)
        shutil.move(str(dam_root), str(stash))
        dam_root.mkdir(parents=True)
        link_or_move(stash, batch_0516, move=move)

    if dam_0417.is_dir():
        link_or_move(dam_0417, batch_0417, move=move)


def migrate_inbox(dms_root: Path, *, move: bool) -> None:
    for old, new in (
        ("dam", "dam/batch_0516"),
        ("dam_0417", "dam/batch_0417"),
    ):
        src = dms_root / "inbox" / old
        dst = dms_root / "inbox" / new
        if src.is_dir():
            link_or_move(src, dst, move=move)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pack-dir", type=Path, required=True)
    p.add_argument("--dms-root", type=Path, help="datasets/dms 根，迁移 inbox")
    p.add_argument("--move", action="store_true")
    args = p.parse_args()
    migrate_pack(args.pack_dir.resolve(), move=args.move)
    if args.dms_root:
        migrate_inbox(args.dms_root.resolve(), move=args.move)
    print("完成。请运行 refresh_yaml.py --task dam 并刷新 catalog。")


if __name__ == "__main__":
    main()

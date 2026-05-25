#!/usr/bin/env python3
"""
Build UFLD-ready dataset under lane0_copy/DATASET from archive train_2025_03_13_mufld.

Layout:
  DATASET/
    images/<src_...>/...frame_XXXXXX.jpg|png
    annotations/segmentation_masks/<src_...>/...frame_XXXXXX.png
    list/train_gt.txt          # 90% train (two columns)
    list/val_gt.txt            # 10% val
    list/test_gt.txt           # held-out labeled test
    list/test.txt              # image-only inference list
    manifest.json
    README.md

Uses hardlinks when possible (same filesystem, no extra disk for file data).

Usage:
  conda activate lane_light
  python build_ufld_dataset.py
  python build_ufld_dataset.py --copy   # physical copy instead of hardlink
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# reuse naming rules
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from rename_ufld_dataset import transform_dir_component, transform_filename  # noqa: E402

DEFAULT_SRC = Path("/home/chengfanglu/DATA/lane0_copy/archive/train_2025_03_13_mufld")
DEFAULT_OUT = Path("/home/chengfanglu/DATA/lane0_copy/DATASET")

IMG_ROOT = "images"
LBL_ROOT = "annotations/segmentation_masks"


def transform_core_rel(rel: str) -> str:
    """Legacy path (no seg_label prefix) -> renamed relative path."""
    rel = rel.lstrip("/").replace("\\", "/")
    if rel.startswith("seg_label/"):
        rel = rel[len("seg_label/") :]
    parts = rel.split("/")
    if not parts:
        return rel
    out = [transform_dir_component(parts[0])]
    for i in range(1, len(parts)):
        comp = parts[i]
        out.append(
            transform_filename(comp) if i == len(parts) - 1 else transform_dir_component(comp)
        )
    return "/".join(out)


def to_image_rel(legacy_img: str) -> str:
    return f"{IMG_ROOT}/{transform_core_rel(legacy_img)}"


def to_mask_rel(legacy_mask: str) -> str:
    return f"{LBL_ROOT}/{transform_core_rel(legacy_mask)}"


def parse_gt_line(line: str) -> tuple[str, str] | None:
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    return parts[0].lstrip("/"), parts[1].lstrip("/")


def link_or_copy(src: Path, dst: Path, use_copy: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.samefile(src):
            return
        raise FileExistsError(f"exists with different file: {dst}")
    if use_copy:
        shutil.copy2(src, dst)
    else:
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--copy", action="store_true", help="Physical copy (uses ~2x disk)")
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    src_root = args.src.resolve()
    out_root = args.out.resolve()
    use_copy = args.copy

    if not src_root.is_dir():
        sys.exit(f"Source not found: {src_root}")

    out_root.mkdir(parents=True, exist_ok=True)
    list_dir = out_root / "list"
    list_dir.mkdir(parents=True, exist_ok=True)

    # --- collect pairs from manifests ---
    train_val_path = src_root / "train_val_gt.txt"
    test_gt_path = src_root / "test_gt.txt"
    test_txt_path = src_root / "test.txt"

    pairs: list[tuple[str, str]] = []
    for line in train_val_path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = parse_gt_line(line)
        if p:
            pairs.append(p)

    test_pairs: list[tuple[str, str]] = []
    for line in test_gt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = parse_gt_line(line)
        if p:
            test_pairs.append(p)

    test_images_only: list[str] = []
    for line in test_txt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = line.strip().lstrip("/")
        if p:
            test_images_only.append(p)

    # unique files to materialize
    img_jobs: dict[str, str] = {}  # legacy -> new rel
    msk_jobs: dict[str, str] = {}
    for img, msk in pairs + test_pairs:
        img_jobs[img] = to_image_rel(img)
        msk_jobs[msk] = to_mask_rel(msk)
    for img in test_images_only:
        img_jobs[img] = to_image_rel(img)

    print(f"Link/copy {len(img_jobs)} images + {len(msk_jobs)} masks -> {out_root}", file=sys.stderr)

    missing = []
    linked_img = linked_msk = 0
    for i, (legacy, new_rel) in enumerate(img_jobs.items()):
        s, d = src_root / legacy, out_root / new_rel
        if not s.is_file():
            missing.append(("image", legacy))
            continue
        link_or_copy(s, d, use_copy)
        linked_img += 1
        if (i + 1) % 20000 == 0:
            print(f"  images {i+1}/{len(img_jobs)}", file=sys.stderr)

    for i, (legacy, new_rel) in enumerate(msk_jobs.items()):
        s, d = src_root / legacy, out_root / new_rel
        if not s.is_file():
            missing.append(("mask", legacy))
            continue
        link_or_copy(s, d, use_copy)
        linked_msk += 1
        if (i + 1) % 20000 == 0:
            print(f"  masks {i+1}/{len(msk_jobs)}", file=sys.stderr)

    # --- train / val split (stratified by source) ---
    by_src: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for img, msk in pairs:
        by_src[img.split("/")[0]].append((to_image_rel(img), to_mask_rel(msk)))

    rng = random.Random(args.seed)
    train_lines: list[str] = []
    val_lines: list[str] = []
    for src_name in sorted(by_src.keys()):
        items = by_src[src_name]
        rng.shuffle(items)
        n_val = max(1, int(len(items) * args.val_ratio)) if len(items) >= 10 else max(0, int(len(items) * args.val_ratio))
        val_items = items[:n_val]
        tr_items = items[n_val:]
        for ir, mr in tr_items:
            train_lines.append(f"{ir} {mr}")
        for ir, mr in val_items:
            val_lines.append(f"{ir} {mr}")

    rng.shuffle(train_lines)
    rng.shuffle(val_lines)

    (list_dir / "train_gt.txt").write_text("\n".join(train_lines) + "\n", encoding="utf-8")
    (list_dir / "val_gt.txt").write_text("\n".join(val_lines) + "\n", encoding="utf-8")

    test_gt_lines = [f"{to_image_rel(i)} {to_mask_rel(m)}" for i, m in test_pairs]
    (list_dir / "test_gt.txt").write_text("\n".join(test_gt_lines) + "\n", encoding="utf-8")

    test_inf_lines = [to_image_rel(i) for i in test_images_only]
    (list_dir / "test.txt").write_text("\n".join(test_inf_lines) + "\n", encoding="utf-8")

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(src_root),
        "output": str(out_root),
        "link_mode": "copy" if use_copy else "hardlink",
        "train_pairs": len(train_lines),
        "val_pairs": len(val_lines),
        "test_gt_pairs": len(test_gt_lines),
        "test_inference_images": len(test_inf_lines),
        "linked_images": linked_img,
        "linked_masks": linked_msk,
        "missing_files": missing[:50],
        "missing_count": len(missing),
        "val_ratio": args.val_ratio,
        "seed": args.seed,
        "ufld_data_root": str(out_root),
        "ufld_train_list": "list/train_gt.txt",
    }
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    readme = f"""# lane0_copy/DATASET — UFLD 训练包

生成自: `{src_root}`

## 目录结构

```
DATASET/
├── images/                              # 原图（清晰命名）
├── annotations/segmentation_masks/      # 分割标签（与 images 镜像路径）
├── list/
│   ├── train_gt.txt                     # 训练（{len(train_lines)} 对）
│   ├── val_gt.txt                       # 验证（{len(val_lines)} 对）
│   ├── test_gt.txt                      # 有标签测试（{len(test_gt_lines)} 对）
│   └── test.txt                         # 仅图像推理（{len(test_inf_lines)} 条）
├── manifest.json
└── README.md
```

## 命名规则

- 来源目录: `src_<类型>_<设备>_<日期>`，例如 `src_cam_zxc_20250628`
- 子目录: `clip_XX` / `scene_XX` / `unit_XX` / `video_*` 等
- 帧文件: `frame_XXXXXX.jpg` / `frame_cam_<id>.jpg`（去掉 `_new` 后缀）

## UFLD 训练

```bash
cd /home/chengfanglu/DATA/BK2/UFLD
# configs/mufld_lane_culane.py 中 data_root 指向本目录
python train.py configs/mufld_lane_culane.py
```

`LaneClsDataset` 读取 `list/train_gt.txt`（两列：图像相对路径、mask 相对路径）。

## 说明

- 文件通过 **{'物理复制' if use_copy else '硬链接'}** 生成，节省磁盘（硬链接与 archive 共享 inode）。
- 有标签评测用 `list/test_gt.txt`，勿与 `list/test.txt` 混用。
"""
    (out_root / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    if missing:
        print(f"WARNING: {len(missing)} missing files (see manifest)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

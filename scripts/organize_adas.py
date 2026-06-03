#!/usr/bin/env python3
"""整理 ADAS 数据集到 HSAP 平台可读格式。

ADAS 数据集目录结构:
  road_datas/wf_batch*/images/  + labels/    ← 标准格式，直接用
  OPEN/ONCE/tvt/{train,val,test}/.../images/  ← 需整理
  VAL_s/.../images/                            ← 需整理

输出: datasets/dms/packs/adas_v1/ 下创建组织好的目录 + 生成 class summary。
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

ARCHIVE = Path("/home/chengfanglu/DATA/workspace/BK2/archive/adas_2d_det_dataset")
DEST = Path("/home/chengfanglu/DATA/HSAP/datasets/dms/packs/adas_v1")
MANIFESTS = Path("/home/chengfanglu/DATA/HSAP/datasets/dms/manifests")

CLASS_NAMES = ["Pedestrain", "Car", "Truck", "Bus", "Motor-vehicles", "Tricycle", "cones"]


def count_yolo_labels(label_dir: Path) -> dict[int, int]:
    """统计 YOLO label 目录中各类别实例数。"""
    counts: dict[int, int] = defaultdict(int)
    if not label_dir.is_dir():
        return dict(counts)
    for txt in label_dir.glob("*.txt"):
        try:
            for line in txt.read_text().strip().splitlines():
                parts = line.strip().split()
                if parts:
                    cls_id = int(float(parts[0]))
                    counts[cls_id] += 1
        except Exception:
            pass
    return dict(counts)


def count_images(img_dir: Path) -> int:
    if not img_dir.is_dir():
        return 0
    return len([f for f in img_dir.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}])


def organize_wf_batches() -> tuple[int, dict[int, int], int]:
    """整理 road_datas/wf_batch*/ 到 adas/sources/ 。返回 (total_images, class_counts, total_boxes)。"""
    sources_dir = DEST / "adas" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    total_imgs = 0
    total_boxes = 0
    class_counts: dict[int, int] = defaultdict(int)

    road_datas = ARCHIVE / "road_datas"
    if not road_datas.is_dir():
        print(f"  ⚠ road_datas not found at {road_datas}")
        return 0, {}, 0

    for batch_dir in sorted(road_datas.iterdir()):
        if not batch_dir.is_dir():
            continue
        img_dir = batch_dir / "images"
        lbl_dir = batch_dir / "labels"
        if not img_dir.is_dir():
            continue

        batch_name = batch_dir.name
        dest_batch = sources_dir / batch_name
        if dest_batch.exists():
            continue  # 已整理过

        n_imgs = count_images(img_dir)
        if n_imgs == 0:
            continue

        dest_batch.mkdir(parents=True, exist_ok=True)
        dest_img = dest_batch / "images"
        dest_lbl = dest_batch / "labels"

        # 使用 symlink 节省磁盘空间
        dest_img.symlink_to(img_dir.resolve())
        if lbl_dir.is_dir():
            dest_lbl.symlink_to(lbl_dir.resolve())
            cc = count_yolo_labels(lbl_dir)
            for cls_id, cnt in cc.items():
                class_counts[cls_id] += cnt
                total_boxes += cnt

        total_imgs += n_imgs
        print(f"  ✓ {batch_name}: {n_imgs} imgs, {sum(cc.values()) if lbl_dir.is_dir() else 0} boxes")

    return total_imgs, dict(class_counts), total_boxes


def organize_once() -> tuple[int, dict[int, int], int]:
    """整理 OPEN/ONCE/tvt/ 到 adas/sources/once_*/ 。"""
    once_dir = ARCHIVE / "OPEN" / "ONCE" / "tvt"
    if not once_dir.is_dir():
        print(f"  ⚠ ONCE not found at {once_dir}")
        return 0, {}, 0

    total_imgs = 0
    total_boxes = 0
    class_counts: dict[int, int] = defaultdict(int)
    sources_dir = DEST / "adas" / "sources"

    for split in ["train", "val", "test"]:
        split_dir = once_dir / split
        if not split_dir.is_dir():
            continue
        for cam_dir in sorted(split_dir.iterdir()):
            if not cam_dir.is_dir():
                continue
            for scene_dir in sorted(cam_dir.iterdir()):
                if not scene_dir.is_dir():
                    continue
                img_dir = scene_dir / "images"
                if not img_dir.is_dir():
                    continue
                n_imgs = count_images(img_dir)
                if n_imgs == 0:
                    continue

                batch_name = f"once_{split}_{cam_dir.name}_{scene_dir.name}"
                dest_batch = sources_dir / batch_name
                if dest_batch.exists():
                    continue

                dest_batch.mkdir(parents=True, exist_ok=True)
                (dest_batch / "images").symlink_to(img_dir.resolve())
                total_imgs += n_imgs
                print(f"  ✓ {batch_name}: {n_imgs} imgs")

    return total_imgs, dict(class_counts), total_boxes


def write_class_summary(total_boxes: dict[int, int]):
    """生成平台可读的 class summary 文件。"""
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    summary_path = MANIFESTS / "dataset_class_summary.txt"

    # 读取已有内容（保留其他任务的统计）
    existing: dict[str, str] = {}
    if summary_path.is_file():
        current_task = None
        for line in summary_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_task = line[1:-1]
                existing[current_task] = ""
            elif current_task:
                existing[current_task] += line + "\n"

    # 生成 adas 统计
    lines = ["[adas]"]
    for cls_id in sorted(total_boxes.keys()):
        name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"class_{cls_id}"
        lines.append(f"{name}: {total_boxes[cls_id]}")
    existing["adas"] = "\n".join(lines[1:]) + "\n"

    # 写回
    with open(summary_path, "w") as f:
        for task, content in existing.items():
            f.write(f"[{task}]\n{content}")
    print(f"  ✓ Class summary written to {summary_path}")


def main():
    print("=== 整理 ADAS 数据集 ===")
    DEST.mkdir(parents=True, exist_ok=True)

    print("\n1. 整理 wf_batch 批次...")
    wf_imgs, wf_classes, wf_boxes = organize_wf_batches()

    print("\n2. 整理 ONCE 数据...")
    once_imgs, once_classes, once_boxes = organize_once()

    # 合并统计
    total_boxes: dict[int, int] = defaultdict(int)
    for cls_id, cnt in wf_classes.items():
        total_boxes[cls_id] += cnt
    for cls_id, cnt in once_classes.items():
        total_boxes[cls_id] += cnt

    print(f"\n=== 整理完成 ===")
    print(f"  wf_batch 图片: {wf_imgs}, 标注框: {wf_boxes}")
    print(f"  ONCE 图片: {once_imgs}")
    print(f"  总标注框: {sum(total_boxes.values())}")
    print(f"  各类别分布: {dict(total_boxes)}")

    print("\n3. 生成 class summary...")
    write_class_summary(dict(total_boxes))

    print("\n✅ 完成！可以刷新 catalog 了")


if __name__ == "__main__":
    main()

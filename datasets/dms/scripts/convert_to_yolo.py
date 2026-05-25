#!/usr/bin/env python3
"""将非标准数据转为 Ultralytics/YOLO 可用格式。"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from stratified_split import collect_yolo_samples, stratified_assign, stratified_assign_classify

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}

DAM_NAMES = [
    "face", "eye_open", "eye_partially_open", "eye_close", "mouth_open",
    "mouth_partially_open", "mouth_close", "side_face", "nod_face", "glasses",
    "sunglasses", "smoke", "phone", "driver", "rise_face",
]
DAM_NAME_TO_ID = {n: i for i, n in enumerate(DAM_NAMES)}


def voc_to_yolo_box(xmin: float, ymin: float, xmax: float, ymax: float, w: int, h: int) -> tuple[float, float, float, float]:
    xc = (xmin + xmax) / 2.0 / w
    yc = (ymin + ymax) / 2.0 / h
    bw = (xmax - xmin) / w
    bh = (ymax - ymin) / h
    return xc, yc, bw, bh


def _classes_from_lines(lines: list[str]) -> set[int]:
    out: set[int] = set()
    for line in lines:
        if line.strip():
            out.add(int(line.split()[0]))
    return out


def convert_dam_voc(
    src_root: Path,
    dst_root: Path,
    val_ratio: float = 0.1,
    seed: int = 42,
    link_images: bool = True,
) -> dict:
    """VOC(xml) -> YOLO，一次写入 train/val，避免二次 move。"""
    src_images = src_root / "images"
    src_labels = src_root / "labels"
    if not src_images.is_dir() or not src_labels.is_dir():
        raise FileNotFoundError(f"expect {src_images} and {src_labels}")

    records: list[tuple[str, Path, list[str]]] = []
    unknown: dict[str, int] = {}
    n_skip, n_empty = 0, 0
    xml_files = sorted(src_labels.glob("*.xml"))
    total = len(xml_files)
    print(f"  解析 xml: {total} 个")

    for i, xml_path in enumerate(xml_files, 1):
        if i % 500 == 0 or i == total:
            print(f"    xml {i}/{total}", flush=True)
        stem = xml_path.stem
        img_src = None
        for ext in IMG_EXTS:
            p = src_images / f"{stem}{ext}"
            if p.is_file():
                img_src = p
                break
        if img_src is None:
            n_skip += 1
            continue

        tree = ET.parse(xml_path)
        root = tree.getroot()
        size = root.find("size")
        w = int(size.findtext("width", "0"))
        h = int(size.findtext("height", "0"))
        if w <= 0 or h <= 0:
            n_skip += 1
            continue

        lines: list[str] = []
        for obj in root.findall("object"):
            name = (obj.findtext("name") or "").strip()
            if name not in DAM_NAME_TO_ID:
                unknown[name] = unknown.get(name, 0) + 1
                continue
            box = obj.find("bndbox")
            xmin = float(box.findtext("xmin", "0"))
            ymin = float(box.findtext("ymin", "0"))
            xmax = float(box.findtext("xmax", "0"))
            ymax = float(box.findtext("ymax", "0"))
            xc, yc, bw, bh = voc_to_yolo_box(xmin, ymin, xmax, ymax, w, h)
            lines.append(f"{DAM_NAME_TO_ID[name]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")

        if not lines:
            n_empty += 1
        records.append((stem, img_src, lines))

    samples = [(stem, _classes_from_lines(lines)) for stem, _, lines in records]
    assignment = stratified_assign(samples, val_ratio=val_ratio, seed=seed, min_val_per_class=1)
    print(f"  写入 YOLO: {len(records)} 对", flush=True)

    img_abs_cache: dict[Path, str] = {}
    for i, (stem, img_src, lines) in enumerate(records, 1):
        if i % 500 == 0 or i == len(records):
            print(f"    write {i}/{len(records)}", flush=True)
        split = assignment.get(stem, "train")
        lab_dst = dst_root / "labels" / split / f"{stem}.txt"
        img_dst = dst_root / "images" / split / img_src.name
        lab_dst.parent.mkdir(parents=True, exist_ok=True)
        img_dst.parent.mkdir(parents=True, exist_ok=True)
        lab_dst.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        if img_dst.exists() or img_dst.is_symlink():
            img_dst.unlink()
        if link_images:
            if img_src not in img_abs_cache:
                img_abs_cache[img_src] = str(img_src.resolve())
            img_dst.symlink_to(img_abs_cache[img_src])
        else:
            shutil.copy2(img_src, img_dst)

    n_val = sum(1 for v in assignment.values() if v == "val")
    yaml_path = dst_root.parent.parent / "configs" / "dam_0417.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    names_yaml = ", ".join(f'"{n}"' for n in DAM_NAMES)
    yaml_path.write_text(
        f"""# DAM 源数据 dam_src_0417 转换 (VOC -> YOLO)
path: {dst_root.resolve()}
train: images/train
val: images/val

nc: {len(DAM_NAMES)}
names: [{names_yaml}]
""",
        encoding="utf-8",
    )

    return {
        "total": len(records),
        "train": len(records) - n_val,
        "val": n_val,
        "empty_labels": n_empty,
        "skipped_no_image": n_skip,
        "unknown_names": unknown,
        "yaml": str(yaml_path),
        "dst": str(dst_root),
    }


def convert_classify_layout(root: Path, val_ratio: float = 0.1, seed: int = 42) -> dict:
    """从 train 按类划出 val（硬链优先，同盘更快）。"""
    train_dir = root / "train"
    if not train_dir.is_dir():
        raise FileNotFoundError(f"missing train/: {train_dir}")

    val_dir = root / "val"
    if val_dir.is_dir() and any(val_dir.iterdir()):
        print(f"  val/ 已存在，跳过: {root}")
        return {"skipped": "val exists"}

    class_dirs = sorted(d for d in train_dir.iterdir() if d.is_dir())
    print(f"  类别数: {len(class_dirs)}", flush=True)
    assignment = stratified_assign_classify(class_dirs, val_ratio, seed, min_val_per_class=1)
    val_items = [(p, sp) for p, sp in assignment.items() if sp == "val"]
    print(f"  划出 val: {len(val_items)} 张", flush=True)

    val_dir.mkdir(parents=True, exist_ok=True)
    moved, linked = 0, 0
    for i, (src_path, _) in enumerate(val_items, 1):
        if i % 2000 == 0 or i == len(val_items):
            print(f"    val {i}/{len(val_items)}", flush=True)
        dst = val_dir / src_path.parent.name / src_path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            continue
        try:
            os.link(src_path, dst)
            src_path.unlink()
            linked += 1
        except OSError:
            shutil.move(str(src_path), str(dst))
            moved += 1

    yaml_path = root.parent.parent / "configs" / "isa_class_0116.yaml"
    yaml_path.write_text(
        f"""# ISA 交通标志分类 (Ultralytics classify)
path: {root.resolve()}
train: train
val: val
test: test
""",
        encoding="utf-8",
    )
    return {"val_total": len(val_items), "hardlink": linked, "move": moved, "yaml": str(yaml_path)}


def verify_yolo_detect(root: Path) -> str:
    for sp in ("train", "val"):
        img_d = root / "images" / sp
        lab_d = root / "labels" / sp
        if not img_d.is_dir() or not lab_d.is_dir():
            return f"missing images|labels/{sp}"
        if not any(img_d.iterdir()):
            return f"empty images/{sp}"
        if not any(lab_d.glob("*.txt")):
            return f"empty labels/{sp}"
    return "ok"


def verify_yolo_pose(root: Path) -> str:
    msg = verify_yolo_detect(root)
    if msg != "ok":
        return msg
    sample = next((root / "labels" / "train").glob("*.txt"), None)
    if sample and len(sample.read_text().split()) < 6:
        return "pose label fields < 6"
    return "ok"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gyp", type=Path, default=Path(__file__).resolve().parents[1] / "gyp")
    p.add_argument("--val-ratio", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--copy-images", action="store_true")
    p.add_argument("--only", choices=("dam", "classify", "verify", "all"), default="all")
    args = p.parse_args()
    gyp = args.gyp.resolve()

    if args.only in ("dam", "all"):
        print("=" * 60)
        print("1) dam_src_0417  VOC -> YOLO  =>  gyp/dam_0417/")
        src = gyp / "dam_src_0417" / "src_data_0417_pick"
        dst = gyp / "dam_0417"
        if dst.exists():
            shutil.rmtree(dst)
        r = convert_dam_voc(src, dst, args.val_ratio, args.seed, link_images=not args.copy_images)
        print(r)

    if args.only in ("classify", "all"):
        print("\n" + "=" * 60)
        print("2) isa_class_0116  分类 -> train/val/test")
        r2 = convert_classify_layout(gyp / "isa_class_0116", args.val_ratio, args.seed)
        print(r2)

    if args.only in ("verify", "all"):
        print("\n" + "=" * 60)
        print("3) 校验")
        for name in ["ddaw_1124", "addw_0523", "isa_detect", "dam_0516", "dam_0417"]:
            root = gyp / name
            if root.is_dir():
                print(f"  {name}: {verify_yolo_detect(root)}")
        print(f"  yoloface-0726: {verify_yolo_pose(gyp / 'yoloface-0726')}")
        ic = gyp / "isa_class_0116"
        if (ic / "val").is_dir():
            print(f"  isa_class_0116: train/val/test ok")

    print("\n完成")


if __name__ == "__main__":
    main()

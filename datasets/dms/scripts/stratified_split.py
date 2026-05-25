#!/usr/bin/env python3
"""
按类别分层划分数据集，避免仅按总量随机切分导致 train/val 类别比例失衡。

YOLO 检测：先按「图像所含类别中最稀有类」决定归属，再对各类别依次划分 val。
分类（文件夹按类）：每个类别目录内独立划分 train/val（或 train/test）。

用法示例：
  # 预览 DDAW 重划分效果（合并现有 train+val 后重分）
  python stratified_split.py yolo --root ../gyp/ddaw_1124 --val-ratio 0.1 --dry-run

  # 执行划分（会移动 images/labels 下文件）
  python stratified_split.py yolo --root ../gyp/ddaw_1124 --val-ratio 0.1 --seed 42

  # 分类数据：从 train 按类划出 val
  python stratified_split.py classify --root ../gyp/isa_class_0116 --val-ratio 0.1 --dry-run
"""

from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}


def _read_yolo_classes(label_path: Path) -> set[int]:
    if not label_path.is_file():
        return set()
    classes: set[int] = set()
    for line in label_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            classes.add(int(line.split()[0]))
        except (ValueError, IndexError):
            continue
    return classes


def _find_image(images_dir: Path, stem: str) -> Path | None:
    for ext in IMG_EXTS:
        p = images_dir / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def collect_yolo_samples(root: Path, splits: tuple[str, ...]) -> list[tuple[str, set[int]]]:
    samples: list[tuple[str, set[int]]] = []
    seen: set[str] = set()
    for split in splits:
        labels_dir = root / "labels" / split
        if not labels_dir.is_dir():
            continue
        for label_path in labels_dir.glob("*.txt"):
            stem = label_path.stem
            if stem in seen:
                continue
            seen.add(stem)
            classes = _read_yolo_classes(label_path)
            samples.append((stem, classes))
    return samples


def val_count_for_class(
    n: int,
    val_ratio: float,
    min_val_per_class: int,
    min_train_per_class: int,
    rare_class_train_floor: int,
) -> int:
    """该类未分配样本数为 n 时，划入 val 的数量（其余进 train）。"""
    if n <= 0:
        return 0
    if n <= rare_class_train_floor:
        if n <= min_train_per_class:
            return 0
        return min(min_val_per_class, n - min_train_per_class)
    n_val = int(round(n * val_ratio))
    if min_val_per_class > 0:
        n_val = max(min_val_per_class, n_val)
    if min_train_per_class > 0 and n > min_train_per_class:
        n_val = min(n_val, n - min_train_per_class)
    return max(0, min(n_val, n))


def stratified_assign(
    samples: list[tuple[str, set[int]]],
    val_ratio: float,
    seed: int,
    min_val_per_class: int = 1,
    min_train_per_class: int = 1,
    rare_class_train_floor: int = 5,
) -> dict[str, str]:
    """按类别分层：从稀有类到常见类，为含该类的未分配图像划分 train/val。"""
    rng = random.Random(seed)
    class_to_stems: dict[int, list[str]] = defaultdict(list)
    stem_to_classes: dict[str, set[int]] = {}

    for stem, classes in samples:
        stem_to_classes[stem] = classes
        for c in classes:
            class_to_stems[c].append(stem)

    no_label = [s for s, c in samples if not c]
    assignment: dict[str, str] = {}

    classes_sorted = sorted(class_to_stems.keys(), key=lambda c: len(set(class_to_stems[c])))

    for c in classes_sorted:
        stems = list(dict.fromkeys(class_to_stems[c]))
        unassigned = [s for s in stems if s not in assignment]
        if not unassigned:
            continue
        rng.shuffle(unassigned)
        n = len(unassigned)
        n_val = val_count_for_class(
            n, val_ratio, min_val_per_class, min_train_per_class, rare_class_train_floor,
        )
        for s in unassigned[:n_val]:
            assignment[s] = "val"
        for s in unassigned[n_val:]:
            assignment[s] = "train"

    for stem in no_label:
        assignment.setdefault(stem, "train")

    for stem, _ in samples:
        assignment.setdefault(stem, "train")

    return assignment


def yolo_class_stats(root: Path, split: str) -> tuple[int, Counter, Counter]:
    labels_dir = root / "labels" / split
    if not labels_dir.is_dir():
        return 0, Counter(), Counter()
    inst = Counter()
    imgs = Counter()
    n_img = 0
    for label_path in labels_dir.glob("*.txt"):
        n_img += 1
        cls_in_img: set[int] = set()
        for line in label_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                c = int(line.split()[0])
            except (ValueError, IndexError):
                continue
            inst[c] += 1
            cls_in_img.add(c)
        for c in cls_in_img:
            imgs[c] += 1
    return n_img, inst, imgs


def print_yolo_stats(root: Path, title: str) -> None:
    print(f"\n=== {title} ===")
    for split in ("train", "val"):
        n_img, inst, imgs = yolo_class_stats(root, split)
        if n_img == 0:
            continue
        print(f"  [{split}] {n_img} images")
        all_cls = sorted(set(inst) | set(imgs))
        for c in all_cls:
            ratio = imgs[c] / n_img * 100 if n_img else 0
            print(
                f"    cls {c}: instances={inst[c]}, images={imgs[c]} "
                f"({imgs[c]}/{n_img}={ratio:.1f}% of split images)"
            )


def apply_yolo_split(
    root: Path,
    assignment: dict[str, str],
    pool_splits: tuple[str, ...] = ("train", "val"),
    dry_run: bool = False,
) -> None:
    """根据 assignment 将图像与标签移动到 images/{train,val}、labels/{train,val}。"""
    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)

    # stem -> (image_path, label_path)
    located: dict[str, tuple[Path | None, Path | None]] = {}
    for split in pool_splits:
        labels_dir = root / "labels" / split
        images_dir = root / "images" / split
        if not labels_dir.is_dir():
            continue
        for label_path in labels_dir.glob("*.txt"):
            stem = label_path.stem
            if stem in located:
                continue
            img = _find_image(images_dir, stem) if images_dir.is_dir() else None
            located[stem] = (img, label_path)

    moves: list[tuple[Path, Path]] = []
    for stem, target_split in assignment.items():
        img_src, lab_src = located.get(stem, (None, None))
        if lab_src is None:
            continue
        lab_dst = root / "labels" / target_split / lab_src.name
        if lab_src.resolve() != lab_dst.resolve():
            moves.append((lab_src, lab_dst))
        if img_src is not None:
            img_dst = root / "images" / target_split / img_src.name
            if img_src.resolve() != img_dst.resolve():
                moves.append((img_src, img_dst))

    print(f"  planned moves: {len(moves)}")
    if dry_run:
        return
    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))


def cmd_yolo(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    if not (root / "images").is_dir():
        raise SystemExit(f"not a YOLO dataset root (missing images/): {root}")

    pool_splits = tuple(s.strip() for s in args.pool_splits.split(","))
    samples = collect_yolo_samples(root, pool_splits)
    print(f"pool: {root}  samples={len(samples)}  val_ratio={args.val_ratio}  seed={args.seed}")

    print_yolo_stats(root, "before")
    assignment = stratified_assign(
        samples,
        val_ratio=args.val_ratio,
        seed=args.seed,
        min_val_per_class=args.min_val_per_class,
        min_train_per_class=args.min_train_per_class,
        rare_class_train_floor=args.rare_class_train_floor,
    )
    n_val = sum(1 for v in assignment.values() if v == "val")
    print(f"\nplanned: train={len(assignment) - n_val}  val={n_val}")

    # 模拟统计（不写盘）
    if args.dry_run:
        tmp_counts: dict[str, Counter] = {"train": Counter(), "val": Counter()}
        tmp_imgs: dict[str, Counter] = {"train": Counter(), "val": Counter()}
        for stem, split in assignment.items():
            for split_name in pool_splits:
                lab = root / "labels" / split_name / f"{stem}.txt"
                if lab.is_file():
                    classes = _read_yolo_classes(lab)
                    break
            else:
                classes = set()
            for c in classes:
                tmp_imgs[split][c] += 1
            for split_name in pool_splits:
                lab = root / "labels" / split_name / f"{stem}.txt"
                if not lab.is_file():
                    continue
                for line in lab.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.strip():
                        try:
                            tmp_counts[split][int(line.split()[0])] += 1
                        except (ValueError, IndexError):
                            pass
                break
        print("\n=== after (simulated) ===")
        for sp in ("train", "val"):
            n = sum(1 for v in assignment.values() if v == sp)
            print(f"  [{sp}] {n} images")
            for c in sorted(set(tmp_counts[sp]) | set(tmp_imgs[sp])):
                print(f"    cls {c}: instances={tmp_counts[sp][c]}, images={tmp_imgs[sp][c]}")
        print("\n=== per-class val ratio (images with class / all images with class) ===")
        print(f"  {'cls':>4}  {'before':>8}  {'after':>8}  {'target':>8}")
        before_val: Counter[int] = Counter()
        before_tot: Counter[int] = Counter()
        for split in pool_splits:
            _, _, imgs = yolo_class_stats(root, split)
            if split == "val":
                before_val.update(imgs)
            before_tot.update(imgs)
        after_tot = Counter()
        after_val = Counter()
        for stem, split in assignment.items():
            for split_name in pool_splits:
                lab = root / "labels" / split_name / f"{stem}.txt"
                if lab.is_file():
                    classes = _read_yolo_classes(lab)
                    break
            else:
                classes = set()
            for c in classes:
                after_tot[c] += 1
                if split == "val":
                    after_val[c] += 1
        for c in sorted(set(before_tot) | set(after_tot)):
            b = before_val[c] / before_tot[c] * 100 if before_tot[c] else 0
            a = after_val[c] / after_tot[c] * 100 if after_tot[c] else 0
            print(f"  {c:4d}  {b:7.1f}%  {a:7.1f}%  {args.val_ratio * 100:7.1f}%")
        return

    apply_yolo_split(root, assignment, pool_splits=pool_splits, dry_run=False)
    print_yolo_stats(root, "after")


def stratified_assign_classify(
    class_dirs: list[Path],
    val_ratio: float,
    seed: int,
    min_val_per_class: int,
    min_train_per_class: int,
    rare_class_train_floor: int,
) -> dict[Path, str]:
    """每个类别目录内独立划分。"""
    rng = random.Random(seed)
    assignment: dict[Path, str] = {}
    for class_dir in sorted(class_dirs):
        files = [p for p in class_dir.iterdir() if p.is_file() and p.suffix in IMG_EXTS]
        rng.shuffle(files)
        n = len(files)
        if n == 0:
            continue
        n_val = val_count_for_class(
            n, val_ratio, min_val_per_class, min_train_per_class, rare_class_train_floor,
        )
        for p in files[:n_val]:
            assignment[p] = "val"
        for p in files[n_val:]:
            assignment[p] = "train"
    return assignment


def resplit_classify_root(
    root: Path,
    val_ratio: float = 0.1,
    seed: int = 42,
    min_val_per_class: int = 1,
    min_train_per_class: int = 1,
    rare_class_train_floor: int = 5,
    dry_run: bool = False,
) -> dict[str, int]:
    """合并 train+val 按类重分 val，保留 test 不动。"""
    pooled: dict[str, list[Path]] = defaultdict(list)
    for split in ("train", "val"):
        sp = root / split
        if not sp.is_dir():
            continue
        for cls_dir in sp.iterdir():
            if not cls_dir.is_dir():
                continue
            for f in cls_dir.iterdir():
                if f.is_file() and f.suffix in IMG_EXTS:
                    pooled[cls_dir.name].append(f)

    staging = root / "_resplit_staging"
    if staging.exists() and not dry_run:
        shutil.rmtree(staging)

    staged_dirs: list[Path] = []
    for cls, files in sorted(pooled.items()):
        seen: dict[str, Path] = {}
        for f in files:
            seen[f.name] = f
        if not seen:
            continue
        cls_staging = staging / cls
        if not dry_run:
            cls_staging.mkdir(parents=True, exist_ok=True)
        for name, f in seen.items():
            dst = cls_staging / name
            if dry_run:
                staged_dirs.append(cls_staging)
                continue
            if f.resolve() != dst.resolve():
                shutil.move(str(f), str(dst))
        if not dry_run:
            staged_dirs.append(cls_staging)

    if dry_run:
        n_tr = n_va = 0
        for cls, files in pooled.items():
            n = len({f.name for f in files})
            n_val = val_count_for_class(
                n, val_ratio, min_val_per_class, min_train_per_class, rare_class_train_floor,
            )
            n_va += n_val
            n_tr += n - n_val
        return {"train": n_tr, "val": n_va, "dry_run": True}

    assignment = stratified_assign_classify(
        staged_dirs, val_ratio, seed, min_val_per_class, min_train_per_class, rare_class_train_floor,
    )
    (root / "train").mkdir(exist_ok=True)
    (root / "val").mkdir(exist_ok=True)
    n_val = 0
    for src_path, sp in assignment.items():
        dst = root / sp / src_path.parent.name / src_path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        shutil.move(str(src_path), str(dst))
        if sp == "val":
            n_val += 1
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    n_train = sum(len(list((root / "train" / c).iterdir())) for c in pooled if (root / "train" / c).is_dir())
    return {"train": n_train, "val": n_val}


def cmd_classify(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    src_split = args.src_split
    src_dir = root / src_split
    if not src_dir.is_dir():
        raise SystemExit(f"missing source split dir: {src_dir}")

    class_dirs = [d for d in src_dir.iterdir() if d.is_dir()]
    files_all = [p for d in class_dirs for p in d.iterdir() if p.is_file() and p.suffix in IMG_EXTS]
    print(f"classify: {root}  classes={len(class_dirs)}  images={len(files_all)}")

    assignment = stratified_assign_classify(
        class_dirs,
        args.val_ratio,
        args.seed,
        args.min_val_per_class,
        args.min_train_per_class,
        args.rare_class_train_floor,
    )
    n_val = sum(1 for v in assignment.values() if v == "val")
    print(f"planned: train={len(assignment) - n_val}  val={n_val}")

    if args.dry_run:
        per_cls: dict[str, Counter] = {"train": Counter(), "val": Counter()}
        for path, sp in assignment.items():
            per_cls[sp][path.parent.name] += 1
        print("\n=== per-class counts (simulated) ===")
        for cls_name in sorted({p.parent.name for p in assignment}):
            tr = per_cls["train"][cls_name]
            va = per_cls["val"][cls_name]
            tot = tr + va
            pct = va / tot * 100 if tot else 0
            print(f"  {cls_name}: train={tr} val={va} (val%={pct:.1f})")
        return

    for target in ("train", "val"):
        (root / target).mkdir(parents=True, exist_ok=True)

    moves = 0
    for src_path, target_split in assignment.items():
        cls_name = src_path.parent.name
        dst_dir = root / target_split / cls_name
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src_path.name
        if src_path.resolve() == dst.resolve():
            continue
        if dst.exists():
            dst.unlink()
        shutil.move(str(src_path), str(dst))
        moves += 1
    print(f"done, moved {moves} files into train/val")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="按类别分层划分 DMS 数据集")
    sub = p.add_subparsers(dest="mode", required=True)

    py = sub.add_parser("yolo", help="YOLO 检测：images/labels 的 train+val")
    py.add_argument("--root", required=True, help="数据集根目录，含 images/ labels/")
    py.add_argument("--val-ratio", type=float, default=0.1)
    py.add_argument("--seed", type=int, default=42)
    py.add_argument("--pool-splits", default="train,val", help="合并哪些 split 后重分")
    py.add_argument("--min-val-per-class", type=int, default=1)
    py.add_argument("--min-train-per-class", type=int, default=1)
    py.add_argument("--rare-class-train-floor", type=int, default=5)
    py.add_argument("--dry-run", action="store_true")
    py.set_defaults(func=cmd_yolo)

    pc = sub.add_parser("classify", help="分类：每类文件夹内独立划分")
    pc.add_argument("--root", required=True)
    pc.add_argument("--src-split", default="train", help="从哪个目录按类采样（如 train）")
    pc.add_argument("--val-ratio", type=float, default=0.1)
    pc.add_argument("--seed", type=int, default=42)
    pc.add_argument("--min-val-per-class", type=int, default=1)
    pc.add_argument("--min-train-per-class", type=int, default=1)
    pc.add_argument("--rare-class-train-floor", type=int, default=5)
    pc.add_argument("--dry-run", action="store_true")
    pc.set_defaults(func=cmd_classify)

    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

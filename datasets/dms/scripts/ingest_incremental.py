#!/usr/bin/env python3
"""
接入新数据：合并进 dataset_bundle/<task>/，默认按类分层重划 train/val。

叠放新批次（推荐）:
  .../dam/sources/20260520_line2/   # images+labels 或 images/train+labels/train
  python ml.py build dms dam --all-sources

inbox 方式仍可用:
  python ml.py add dms dam --src /path/to/batch
  python ml.py build dms dam --batch <name>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from pack_registry import task_data_root as pack_task_data_root  # noqa: E402
from convert_to_yolo import convert_dam_voc  # noqa: E402
from stratified_split import (  # noqa: E402
    apply_yolo_split,
    collect_yolo_samples,
    print_yolo_stats,
    resplit_classify_root,
    stratified_assign,
)

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}


def load_registry(root: Path) -> dict:
    return yaml.safe_load((root / "datasets.registry.yaml").read_text(encoding="utf-8"))


def split_kwargs(reg: dict, args: argparse.Namespace) -> dict:
    s = reg.get("split") or {}
    return {
        "val_ratio": args.val_ratio if args.val_ratio is not None else float(s.get("val_ratio", 0.1)),
        "seed": args.seed if args.seed is not None else int(s.get("seed", 42)),
        "min_val_per_class": int(s.get("min_val_per_class", 1)),
        "min_train_per_class": int(s.get("min_train_per_class", 1)),
        "rare_class_train_floor": int(s.get("rare_class_train_floor", 5)),
    }


def sources_dir(data_root: Path, reg: dict) -> Path:
    sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
    return data_root / sub


def ingested_dir(data_root: Path, reg: dict) -> Path:
    rel = (reg.get("ingest") or {}).get("ingested_subdir", "sources/_ingested")
    return (data_root / rel).resolve()


def list_pending_sources(data_root: Path, reg: dict) -> list[Path]:
    src_root = sources_dir(data_root, reg)
    if not src_root.is_dir():
        return []
    ing = ingested_dir(data_root, reg)
    skip = {ing.name, "_ingested", "_merged"}
    return sorted(
        p
        for p in src_root.iterdir()
        if p.is_dir() and p.name not in skip and not p.name.startswith(".")
    )


def archive_source_batch(src: Path, data_root: Path, reg: dict, dry_run: bool) -> str | None:
    """若 src 在 sources/ 下，合并后移到 sources/_ingested/。"""
    src_root = sources_dir(data_root, reg).resolve()
    try:
        src.resolve().relative_to(src_root)
    except ValueError:
        return None
    dst_base = ingested_dir(data_root, reg)
    dst = dst_base / src.name
    if dry_run:
        return str(dst)
    dst_base.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst = dst_base / f"{src.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.move(str(src), str(dst))
    return str(dst)


def run_stratified_resplit(
    data_root: Path,
    tcfg: dict,
    sk: dict,
    dry_run: bool = False,
) -> dict | None:
    if dry_run:
        return None
    if tcfg["type"] in ("detect", "pose"):
        samples = collect_yolo_samples(data_root, ("train", "val"))
        assign = stratified_assign(samples, **sk)
        apply_yolo_split(data_root, assign, pool_splits=("train", "val"), dry_run=False)
        print_yolo_stats(data_root, "after stratified resplit (per-class)")
        return {
            "train": sum(1 for v in assign.values() if v == "train"),
            "val": sum(1 for v in assign.values() if v == "val"),
        }
    if tcfg["type"] == "classify":
        return resplit_classify_root(data_root, dry_run=False, **sk)
    return None


def find_image(images_dirs: list[Path], stem: str) -> Path | None:
    for d in images_dirs:
        if not d.is_dir():
            continue
        for ext in IMG_EXTS:
            p = d / f"{stem}{ext}"
            if p.is_file():
                return p
    return None


def resolve_yolo_layout(src: Path) -> tuple[list[Path], list[Path], bool]:
    if (src / "images" / "train").is_dir():
        return [src / "images" / "train"], [src / "labels" / "train"], False
    if (src / "images").is_dir() and (src / "labels").is_dir():
        voc = any((src / "labels").glob("*.xml"))
        return [src / "images"], [src / "labels"], voc
    raise SystemExit(
        f"无法识别 YOLO 目录: {src}\n"
        "需要 images/train+labels/train 或 images+labels"
    )


def resolve_classify_layout(src: Path) -> Path:
    if (src / "train").is_dir() and any((src / "train").iterdir()):
        return src / "train"
    if any(d.is_dir() for d in src.iterdir()):
        return src
    raise SystemExit(f"无法识别分类目录: {src}\n需要 train/类名/*.jpg 或 类名/*.jpg")


def file_md5(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def existing_yolo_index(gyp_root: Path) -> tuple[set[str], dict[str, str]]:
    """stem -> md5 of label file（用于去重）。"""
    stems: set[str] = set()
    md5s: dict[str, str] = {}
    for sp in ("train", "val"):
        lab_d = gyp_root / "labels" / sp
        if not lab_d.is_dir():
            continue
        for lab in lab_d.glob("*.txt"):
            stems.add(lab.stem)
            md5s[lab.stem] = file_md5(lab)
    return stems, md5s


def validate_detect_label(text: str, nc: int) -> str | None:
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 5:
            return f"line {i}: fields={len(parts)} < 5"
        cid = int(parts[0])
        if cid < 0 or cid >= nc:
            return f"line {i}: class {cid} not in [0,{nc - 1}]"
    return None


def validate_pose_label(text: str, kpt_shape: list[int]) -> str | None:
    nk, nd = kpt_shape
    min_f = 5 + nk * nd
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        n = len(line.split())
        if n < min_f:
            return f"line {i}: pose fields={n} < {min_f} (kpt_shape={kpt_shape})"
    return None


def validate_label(path: Path, tcfg: dict) -> str | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    typ = tcfg["type"]
    if typ == "detect":
        return validate_detect_label(text, int(tcfg["nc"]))
    if typ == "pose":
        return validate_pose_label(text, tcfg.get("kpt_shape", [37, 3]))
    return None


def copy_pair(lab: Path, img: Path, dst_lab: Path, dst_img: Path, copy: bool) -> None:
    dst_lab.parent.mkdir(parents=True, exist_ok=True)
    dst_img.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lab, dst_lab)
    if copy:
        shutil.copy2(img, dst_img)
    else:
        if dst_img.exists() or dst_img.is_symlink():
            dst_img.unlink()
        dst_img.symlink_to(img.resolve())


def ingest_yolo(
    task: str,
    tcfg: dict,
    data_root: Path,
    src: Path,
    sk: dict,
    to_split: str = "train",
    resplit: bool = False,
    dry_run: bool = False,
    copy: bool = False,
    dedup: str = "stem",
) -> dict:
    img_dirs, lab_dirs, is_voc = resolve_yolo_layout(src)
    staging_parent = None

    if is_voc:
        if tcfg["type"] != "detect":
            raise SystemExit("VOC xml 仅支持 detect 任务（dam 各批次等）")
        staging = data_root.parent / "_staging_voc" / task
        staging_parent = staging.parent
        if staging.exists() and not dry_run:
            shutil.rmtree(staging)
        if not dry_run:
            convert_dam_voc(src, staging, val_ratio=0.0, seed=sk["seed"], link_images=not copy)
        img_dirs = [staging / "images" / "train"]
        lab_dirs = [staging / "labels" / "train"]

    known_stems, known_md5 = existing_yolo_index(data_root)
    dst_img = data_root / "images" / to_split
    dst_lab = data_root / "labels" / to_split

    added, skipped_dup, skipped_bad, skipped_no_img = 0, 0, 0, 0
    bad_samples: list[str] = []

    for lab in sorted(lab_dirs[0].glob("*.txt")):
        err = validate_label(lab, tcfg)
        if err:
            skipped_bad += 1
            if len(bad_samples) < 5:
                bad_samples.append(f"{lab.name}: {err}")
            continue

        stem = lab.stem
        lab_md5 = file_md5(lab) if dedup == "md5" else None
        if stem in known_stems:
            if dedup == "md5" and known_md5.get(stem) != lab_md5:
                pass  # 同名不同内容，仍跳过并计 dup；可改为告警
            skipped_dup += 1
            continue

        img = find_image(img_dirs, stem)
        if img is None:
            skipped_no_img += 1
            continue

        if not dry_run:
            copy_pair(lab, img, dst_lab / f"{stem}.txt", dst_img / img.name, copy)
        added += 1
        known_stems.add(stem)
        if lab_md5:
            known_md5[stem] = lab_md5

    resplit_info = None
    if resplit and not dry_run and tcfg["type"] in ("detect", "pose"):
        resplit_info = run_stratified_resplit(data_root, tcfg, sk, dry_run=False)

    if staging_parent and staging_parent.exists() and not dry_run:
        shutil.rmtree(staging_parent, ignore_errors=True)

    return {
        "task": task,
        "type": tcfg["type"],
        "added": added,
        "skipped_dup": skipped_dup,
        "skipped_bad_label": skipped_bad,
        "skipped_no_img": skipped_no_img,
        "bad_samples": bad_samples,
        "to_split": to_split,
        "resplit": resplit_info,
        "dry_run": dry_run,
    }


def existing_classify_names(gyp_root: Path, split: str) -> set[str]:
    d = gyp_root / split
    if not d.is_dir():
        return set()
    return {x.name for x in d.iterdir() if x.is_dir()}


def ingest_classify(
    task: str,
    tcfg: dict,
    data_root: Path,
    src: Path,
    sk: dict,
    to_split: str = "train",
    resplit: bool = False,
    dry_run: bool = False,
    copy: bool = True,
) -> dict:
    src_root = resolve_classify_layout(src)
    dst_root = data_root / to_split
    added, skipped_dup, new_classes = 0, 0, []

    for cls_dir in sorted(d for d in src_root.iterdir() if d.is_dir()):
        dst_cls = dst_root / cls_dir.name
        if not dst_cls.exists() and not dry_run:
            new_classes.append(cls_dir.name)
        for img in cls_dir.iterdir():
            if not img.is_file() or img.suffix not in IMG_EXTS:
                continue
            dst = dst_cls / img.name
            if dst.exists():
                skipped_dup += 1
                continue
            if dry_run:
                added += 1
                continue
            dst_cls.mkdir(parents=True, exist_ok=True)
            if copy:
                shutil.copy2(img, dst)
            else:
                dst.symlink_to(img.resolve())
            added += 1

    resplit_info = None
    if resplit and not dry_run:
        resplit_info = run_stratified_resplit(data_root, tcfg, sk, dry_run=False)

    return {
        "task": task,
        "type": "classify",
        "added": added,
        "skipped_dup": skipped_dup,
        "new_classes": new_classes[:20],
        "new_class_count": len(new_classes),
        "to_split": to_split,
        "resplit": resplit_info,
        "dry_run": dry_run,
    }


def append_log(root: Path, record: dict) -> None:
    log = root / "manifests" / "ingest_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    record["ts"] = datetime.now(timezone.utc).isoformat()
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_refresh(root: Path) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "refresh_yaml.py"), "--root", str(root)],
        check=True,
    )


def ingest_one(
    root: Path,
    reg: dict,
    task: str,
    src: Path,
    args: argparse.Namespace,
) -> dict:
    from task_registry import get_mode_config, resolve_task_id

    submode = getattr(args, "mode", None) or getattr(args, "submode", None)
    task, submode = resolve_task_id(task, submode)
    tcfg = get_mode_config(task, submode, reg)
    pack = getattr(args, "pack", None) or "dms_v1"
    data_root = pack_task_data_root(root, pack, tcfg["task_dir"])
    sk = split_kwargs(reg, args)
    print(f"\n=== pack={pack} task={task} type={tcfg['type']} src={src} ===")
    print(
        f"  split: val_ratio={sk['val_ratio']} min_train={sk['min_train_per_class']} "
        f"rare_floor={sk['rare_class_train_floor']} resplit={args.resplit}"
    )

    if tcfg["type"] == "classify":
        result = ingest_classify(
            task, tcfg, data_root, src,
            sk=sk,
            to_split=args.to, resplit=args.resplit,
            dry_run=args.dry_run, copy=args.copy,
        )
    else:
        result = ingest_yolo(
            task, tcfg, data_root, src,
            sk=sk,
            to_split=args.to, resplit=args.resplit,
            dry_run=args.dry_run, copy=args.copy, dedup=args.dedup,
        )

    if not args.dry_run:
        archived = archive_source_batch(src, data_root, reg, dry_run=False)
        if archived:
            result["archived_to"] = archived
            print(f"  archived source -> {archived}")

    print(result)
    return result


def ingest_extra_train(root: Path, reg: dict, task: str, args: argparse.Namespace) -> list[dict]:
    tcfg = reg["tasks"][task]
    results = []
    for ep in tcfg.get("extra_train") or []:
        src = Path(ep)
        if not src.is_absolute():
            src = (root / ep).resolve()
        if not src.is_dir():
            print(f"  skip extra_train (missing): {src}")
            continue
        results.append(ingest_one(root, reg, task, src, args))
    return results


def ingest_all_sources(root: Path, reg: dict, task: str, args: argparse.Namespace) -> None:
    tcfg = reg["tasks"][task]
    pack = getattr(args, "pack", None) or "dms_v1"
    data_root = pack_task_data_root(root, pack, tcfg["task_dir"])
    batches = list_pending_sources(data_root, reg)
    if not batches:
        print(f"  sources 为空: {sources_dir(data_root, reg)}")
        return
    print(f"\n>>> sources {task}: {len(batches)} batch(es)")
    for batch in batches:
        ingest_one(root, reg, task, batch, args)
        if not args.dry_run:
            append_log(root, {"src": str(batch), "task": task, "pack": pack, "via": "sources"})


def ingest_all_inbox(root: Path, reg: dict, args: argparse.Namespace) -> None:
    from task_registry import inbox_dir

    pack = getattr(args, "pack", None) or "dms_v1"
    for task, tcfg in reg["tasks"].items():
        if tcfg.get("type") == "multi":
            for mode in (tcfg.get("modes") or {}):
                inbox = inbox_dir(root, task, mode, reg)
                if not inbox.is_dir():
                    continue
                batches = sorted(d for d in inbox.iterdir() if d.is_dir())
                if not batches:
                    continue
                print(f"\n>>> inbox {task}/{mode}: {len(batches)} batch(es)")
                args.submode = mode
                for batch in batches:
                    ingest_one(root, reg, task, batch, args)
                    if not args.dry_run:
                        append_log(root, {"src": str(batch), "task": task, "mode": mode, "pack": pack, "via": "inbox"})
        else:
            inbox = inbox_dir(root, task, None, reg)
            if not inbox.is_dir():
                continue
            batches = sorted(d for d in inbox.iterdir() if d.is_dir())
            if not batches:
                continue
            print(f"\n>>> inbox {task}: {len(batches)} batch(es)")
            for batch in batches:
                ingest_one(root, reg, task, batch, args)
                if not args.dry_run:
                    append_log(root, {"src": str(batch), "task": task, "pack": pack, "via": "inbox"})


def main() -> None:
    p = argparse.ArgumentParser(description="DMS 全任务增量接入")
    p.add_argument("--task", help="registry 任务名（forward 等 multi 任务需配合 --submode）")
    p.add_argument("--submode", choices=("detect", "classify"), help="multi 任务子模式，如 forward 的 detect/classify")
    p.add_argument("--src", type=Path, help="新数据目录")
    p.add_argument("--all-inbox", action="store_true", help="处理所有 inbox/<task>/* 批次")
    p.add_argument("--all-sources", action="store_true", help="处理任务 data/sources/* 下所有待合并批次")
    p.add_argument("--sync-extra", action="store_true", help="合并 registry.extra_train 中所有路径")
    p.add_argument("--to", default="train", choices=("train", "val"))
    p.add_argument("--no-resplit", action="store_true", help="跳过重划分（默认按 registry.split.resplit_after_ingest）")
    p.add_argument("--val-ratio", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--copy", action="store_true")
    p.add_argument("--dedup", choices=("stem", "md5"), default="stem")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true", help="完成后运行 refresh_yaml.py")
    p.add_argument("--pack", default="dms_v1", help="写入的数据包名（见 data_packs.yaml）")
    p.add_argument("--root", type=Path, default=DATASET_ROOT)
    args = p.parse_args()

    root = args.root.resolve()
    reg = load_registry(root)
    split_cfg = reg.get("split") or {}
    if args.val_ratio is None:
        args.val_ratio = float(split_cfg.get("val_ratio", 0.1))
    if args.seed is None:
        args.seed = int(split_cfg.get("seed", 42))
    if args.no_resplit:
        args.resplit = False
    else:
        args.resplit = bool(split_cfg.get("resplit_after_ingest", True))

    if args.all_sources:
        if not args.task:
            raise SystemExit("--all-sources 需要 --task")
        ingest_all_sources(root, reg, args.task, args)
        if args.refresh and not args.dry_run:
            run_refresh(root)
        return

    if args.all_inbox:
        ingest_all_inbox(root, reg, args)
        if args.refresh and not args.dry_run:
            run_refresh(root)
        return

    if args.sync_extra:
        for task in reg["tasks"]:
            ingest_extra_train(root, reg, task, args)
        if args.refresh and not args.dry_run:
            run_refresh(root)
        return

    if not args.task or not args.src:
        raise SystemExit("需要 --task + --src，或 --all-inbox / --all-sources，或 --sync-extra")

    if args.task not in reg["tasks"]:
        raise SystemExit(f"未知 task: {args.task}，可选: {list(reg['tasks'])}")

    src = args.src.resolve()
    if not src.is_dir():
        raise SystemExit(f"源目录不存在: {src}")

    result = ingest_one(root, reg, args.task, src, args)
    if not args.dry_run:
        append_log(root, {"src": str(src), "pack": pack, **result})
        if args.refresh:
            run_refresh(root)
        else:
            print("提示: 可运行 python scripts/refresh_yaml.py")


def promote_inbox_batch(
    *,
    root: Path,
    task: str,
    pack: str,
    src: Path,
    mode: str | None = None,
    dry_run: bool = False,
    refresh: bool = True,
    copy: bool = False,
) -> dict:
    """Programmatic inbox batch promote (used by Pack Promote SDK)."""
    reg = load_registry(root.resolve())
    split_cfg = reg.get("split") or {}
    ns = argparse.Namespace(
        task=task,
        submode=mode,
        mode=mode,
        pack=pack,
        dry_run=dry_run,
        copy=copy,
        to="train",
        val_ratio=float(split_cfg.get("val_ratio", 0.1)),
        seed=int(split_cfg.get("seed", 42)),
        resplit=bool(split_cfg.get("resplit_after_ingest", True)),
        dedup="stem",
    )
    result = ingest_one(root.resolve(), reg, task, src.resolve(), ns)
    if not dry_run:
        append_log(root.resolve(), {"src": str(src), "pack": pack, **result})
        if refresh:
            run_refresh(root.resolve())
    return result


if __name__ == "__main__":
    main()

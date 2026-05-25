"""批次元数据 batch.meta.yaml 与目录结构推断。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

META_FILENAME = "batch.meta.yaml"
SCHEMA = "huaxu-batch-v1"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}


def count_images(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    n = 0
    for p in dir_path.rglob("*"):
        if p.is_file() and p.suffix in IMG_EXTS:
            n += 1
    return n


def count_label_files(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    n = 0
    for p in dir_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".txt", ".xml"):
            n += 1
    return n


def dms_has_images(batch_dir: Path) -> bool:
    for sub in ("images", "images/train"):
        if count_images(batch_dir / sub) > 0:
            return True
    return False


def dms_has_labels(batch_dir: Path) -> bool:
    for sub in ("labels", "labels/train"):
        d = batch_dir / sub
        if d.is_dir() and count_label_files(d) > 0:
            return True
    return False


def infer_dms_stage(batch_dir: Path) -> str:
    has_img = dms_has_images(batch_dir)
    has_lab = dms_has_labels(batch_dir)
    if has_img and has_lab:
        return "returned"
    if has_img:
        return "raw_pool"
    return "raw_pool"


def infer_lane_stage(path: Path) -> str:
    if (path / "list" / "train_gt.txt").is_file():
        return "ingested"
    if (path / "train_val_gt.txt").is_file():
        return "returned"
    if any(path.glob("**/train_val_gt.txt")):
        return "returned"
    if count_images(path) > 0:
        return "raw_pool"
    return "raw_pool"


def read_meta(batch_dir: Path) -> dict[str, Any] | None:
    p = batch_dir / META_FILENAME
    if not p.is_file():
        return None
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_meta(batch_dir: Path, data: dict[str, Any]) -> Path:
    batch_dir.mkdir(parents=True, exist_ok=True)
    data.setdefault("schema", SCHEMA)
    p = batch_dir / META_FILENAME
    p.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return p


def enrich_batch(
    batch_dir: Path,
    *,
    project: str,
    task: str | None = None,
    pack: str | None = None,
    batch: str,
    location: str,
) -> dict[str, Any]:
    meta = read_meta(batch_dir) or {}
    if project == "dms":
        stage = meta.get("stage") or infer_dms_stage(batch_dir)
        img_n = meta.get("counts", {}).get("images")
        lab_n = meta.get("counts", {}).get("labels")
        if img_n is None:
            img_n = count_images(batch_dir / "images") + count_images(batch_dir / "images" / "train")
        if lab_n is None:
            lab_n = count_label_files(batch_dir / "labels") + count_label_files(batch_dir / "labels" / "train")
        fmt = meta.get("format", "yolo")
    else:
        stage = meta.get("stage") or infer_lane_stage(batch_dir)
        img_n = meta.get("counts", {}).get("images") or count_images(batch_dir)
        lab_n = meta.get("counts", {}).get("labels")
        fmt = meta.get("format", "ufld_archive")
        if (batch_dir / "list" / "train_gt.txt").is_file():
            try:
                lab_n = sum(1 for _ in (batch_dir / "list" / "train_gt.txt").open(encoding="utf-8"))
            except OSError:
                lab_n = lab_n or 0

    return {
        "project": project,
        "task": task or meta.get("task"),
        "pack": pack or meta.get("pack"),
        "batch": batch,
        "stage": stage,
        "location": location,
        "path": str(batch_dir.resolve()),
        "engineer": meta.get("engineer"),
        "format": fmt,
        "counts": {"images": img_n, "labels": lab_n},
        "has_meta": bool(meta),
        "next_cli": suggest_cli(project, task, pack, batch, stage, location),
    }


def suggest_cli(
    project: str,
    task: str | None,
    pack: str | None,
    batch: str,
    stage: str,
    location: str,
) -> str:
    if project == "dms":
        p = pack or "dms_v2"
        t = task or "<task>"
        if location == "inbox" and stage == "returned":
            return f"python as.py build dms {t} --pack {p} --batch {batch}"
        if location == "sources" and stage == "returned":
            return f"python as.py build dms {t} --pack {p} --all-sources"
        if stage == "raw_pool":
            return f"# 送标完成后放入 labels，或: python as.py register-batch dms {t} --batch {batch} --stage returned"
        return f"python as.py build dms {t} --pack {p}"
    if stage == "returned":
        return "python as.py add lane --src <archive> --engineer <name> --date YYYYMMDD"
    if stage == "ingested":
        return f"python as.py enable lane {pack or '<pack>'} && python as.py build lane"
    return "python as.py add lane --src <path> --engineer <name> --date YYYYMMDD"

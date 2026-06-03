"""DMS inbox 原图批次（如 addw/ddaw：仅有 images/，待送标，无 YOLO/COCO 标注）。"""
from __future__ import annotations

from pathlib import Path

from as_platform.data.batch import count_images, dms_has_images
from as_platform.data.ingest.base import IngestAdapter, IngestContext, NormalizedDataset


def _count_images(path: Path) -> int:
    return count_images(path)


def _split_image_counts(root: Path) -> dict[str, int]:
    train = _count_images(root / "images" / "train")
    val = _count_images(root / "images" / "val")
    test = _count_images(root / "images" / "test")
    if train + val + test == 0:
        train = _count_images(root / "images")
    if train + val + test == 0 and root.name == "images":
        train = _count_images(root / "train")
        val = _count_images(root / "val")
        test = _count_images(root / "test")
        if train + val + test == 0:
            train = _count_images(root)
    if train + val + test == 0 and (root / "train").is_dir():
        train = _count_images(root / "train")
        val = _count_images(root / "val")
        test = _count_images(root / "test")
    return {"train": train, "val": val, "test": test}


def _has_label_txts(root: Path) -> bool:
    for sub in ("labels", "labels/train"):
        d = root / sub
        if d.is_dir() and any(d.rglob("*.txt")):
            return True
    return False


def _is_inbox_raw_layout(root: Path) -> bool:
    if _has_label_txts(root):
        return False
    if dms_has_images(root):
        return True
    if root.name == "images" and (_count_images(root / "train") > 0 or _count_images(root) > 0):
        return True
    if (root / "train").is_dir() and _count_images(root / "train") > 0:
        return True
    if _count_images(root) > 0 and not (root / "images").is_dir() and not (root / "labels").is_dir():
        return True
    return False


class DmsInboxRawAdapter(IngestAdapter):
    format_id = "dms_inbox_raw"
    projects = ("dms",)

    def can_handle(self, ctx: IngestContext) -> bool:
        return _is_inbox_raw_layout(ctx.source_path)

    def inspect(self, ctx: IngestContext) -> NormalizedDataset:
        root = ctx.source_path
        split_counts = _split_image_counts(root)
        sample_count = sum(split_counts.values())
        warnings: list[str] = []
        if sample_count == 0:
            warnings.append(
                "未找到图片；请填批次根目录（含 images/train/）或 images/、train/ 目录"
            )

        artifacts: list[str] = []
        if (root / "images").is_dir():
            artifacts.append("images/")
        elif (root / "train").is_dir():
            artifacts.append("train/（将规范为 images/train）")
        elif root.name == "images":
            artifacts.append("images/")

        return NormalizedDataset(
            format_id=self.format_id,
            project=ctx.project,
            task=ctx.task,
            source_path=str(root),
            split_counts=split_counts,
            sample_count=sample_count,
            annotation_count=0,
            artifacts=artifacts,
            warnings=warnings,
            extra={"stage_hint": "raw_pool"},
        )

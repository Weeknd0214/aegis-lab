"""DMS YOLO-style dataset adapter."""
from __future__ import annotations

from pathlib import Path

from as_platform.data.ingest.base import IngestAdapter, IngestContext, NormalizedDataset

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}


def _count_images(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for p in path.rglob("*") if p.is_file() and p.suffix in IMG_EXTS)


def _count_txt(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for p in path.rglob("*.txt") if p.is_file())


class DmsYoloAdapter(IngestAdapter):
    format_id = "dms_yolo"
    projects = ("dms",)

    def can_handle(self, ctx: IngestContext) -> bool:
        root = ctx.source_path
        return (
            (root / "images").is_dir()
            and (root / "labels").is_dir()
        ) or (
            (root / "images" / "train").is_dir()
            and (root / "labels" / "train").is_dir()
        )

    def inspect(self, ctx: IngestContext) -> NormalizedDataset:
        root = ctx.source_path
        train_images = _count_images(root / "images" / "train")
        val_images = _count_images(root / "images" / "val")
        test_images = _count_images(root / "images" / "test")
        if train_images + val_images + test_images == 0:
            # fallback single-folder dataset
            train_images = _count_images(root / "images")
        train_labels = _count_txt(root / "labels" / "train")
        val_labels = _count_txt(root / "labels" / "val")
        test_labels = _count_txt(root / "labels" / "test")
        if train_labels + val_labels + test_labels == 0:
            train_labels = _count_txt(root / "labels")

        warnings: list[str] = []
        if train_images == 0:
            warnings.append("train split has no images")
        if train_labels == 0:
            warnings.append("train split has no labels")

        return NormalizedDataset(
            format_id=self.format_id,
            project=ctx.project,
            task=ctx.task,
            source_path=str(root),
            split_counts={"train": train_images, "val": val_images, "test": test_images},
            sample_count=train_images + val_images + test_images,
            annotation_count=train_labels + val_labels + test_labels,
            artifacts=["images/", "labels/"],
            warnings=warnings,
        )

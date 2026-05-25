"""Lane mask + list txt adapter."""
from __future__ import annotations

from pathlib import Path

from as_platform.data.ingest.base import IngestAdapter, IngestContext, NormalizedDataset


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


class LaneMaskAdapter(IngestAdapter):
    format_id = "lane_mask"
    projects = ("lane",)

    def can_handle(self, ctx: IngestContext) -> bool:
        root = ctx.source_path
        return (root / "list" / "train_gt.txt").is_file() or (root / "train_val_gt.txt").is_file()

    def inspect(self, ctx: IngestContext) -> NormalizedDataset:
        root = ctx.source_path
        train = _line_count(root / "list" / "train_gt.txt")
        val = _line_count(root / "list" / "val_gt.txt")
        test = _line_count(root / "list" / "test_gt.txt")
        if train == 0 and (root / "train_val_gt.txt").is_file():
            train = _line_count(root / "train_val_gt.txt")

        warnings: list[str] = []
        if train == 0:
            warnings.append("train split list is empty")

        return NormalizedDataset(
            format_id=self.format_id,
            project=ctx.project,
            task=ctx.task,
            source_path=str(root),
            split_counts={"train": train, "val": val, "test": test},
            sample_count=train + val + test,
            annotation_count=train + val + test,
            artifacts=["list/train_gt.txt", "list/val_gt.txt", "list/test_gt.txt"],
            warnings=warnings,
        )

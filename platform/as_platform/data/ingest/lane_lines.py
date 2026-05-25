"""Lane .lines.txt adapter."""
from __future__ import annotations

from pathlib import Path

from as_platform.data.ingest.base import IngestAdapter, IngestContext, NormalizedDataset


class LaneLinesAdapter(IngestAdapter):
    format_id = "lane_lines"
    projects = ("lane",)

    def can_handle(self, ctx: IngestContext) -> bool:
        root = ctx.source_path
        return any(root.rglob("*.lines.txt"))

    def inspect(self, ctx: IngestContext) -> NormalizedDataset:
        root = ctx.source_path
        line_files = list(root.rglob("*.lines.txt"))
        split_counts = {"train": len(line_files), "val": 0, "test": 0}
        warnings: list[str] = []
        if not line_files:
            warnings.append("no *.lines.txt found")
        return NormalizedDataset(
            format_id=self.format_id,
            project=ctx.project,
            task=ctx.task,
            source_path=str(root),
            split_counts=split_counts,
            sample_count=len(line_files),
            annotation_count=len(line_files),
            artifacts=["*.lines.txt"],
            warnings=warnings,
        )

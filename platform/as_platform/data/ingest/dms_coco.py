"""DMS COCO-format adapter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from as_platform.data.ingest.base import IngestAdapter, IngestContext, NormalizedDataset

COCO_NAMES = ("instances_train.json", "instances_val.json", "instances_test.json", "annotations.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class DmsCocoAdapter(IngestAdapter):
    format_id = "dms_coco"
    projects = ("dms",)

    def _find_coco_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for name in COCO_NAMES:
            p = root / "annotations" / name
            if p.is_file():
                files.append(p)
        for name in COCO_NAMES:
            p = root / name
            if p.is_file():
                files.append(p)
        return files

    def can_handle(self, ctx: IngestContext) -> bool:
        root = ctx.source_path
        return len(self._find_coco_files(root)) > 0

    def inspect(self, ctx: IngestContext) -> NormalizedDataset:
        root = ctx.source_path
        files = self._find_coco_files(root)
        split_counts = {"train": 0, "val": 0, "test": 0}
        ann_count = 0
        categories: set[str] = set()
        warnings: list[str] = []
        for f in files:
            data = _read_json(f)
            if not data:
                warnings.append(f"failed to parse {f.name}")
                continue
            images = data.get("images") or []
            anns = data.get("annotations") or []
            cats = data.get("categories") or []
            ann_count += len(anns)
            for c in cats:
                name = c.get("name")
                if isinstance(name, str):
                    categories.add(name)
            lower = f.name.lower()
            if "train" in lower:
                split_counts["train"] += len(images)
            elif "val" in lower:
                split_counts["val"] += len(images)
            elif "test" in lower:
                split_counts["test"] += len(images)
            else:
                split_counts["train"] += len(images)

        return NormalizedDataset(
            format_id=self.format_id,
            project=ctx.project,
            task=ctx.task,
            source_path=str(root),
            split_counts=split_counts,
            sample_count=sum(split_counts.values()),
            annotation_count=ann_count,
            artifacts=[self._artifact_name(root, f) for f in files],
            warnings=warnings,
            extra={"categories": sorted(categories)},
        )

    @staticmethod
    def _artifact_name(root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return path.name

"""Adapter registry and auto detection for uploaded datasets."""
from __future__ import annotations

from pathlib import Path

from as_platform.data.ingest.base import IngestAdapter, IngestContext, NormalizedDataset
from as_platform.data.ingest.dms_coco import DmsCocoAdapter
from as_platform.data.ingest.dms_inbox_raw import DmsInboxRawAdapter
from as_platform.data.ingest.dms_yolo import DmsYoloAdapter
from as_platform.data.ingest.lane_lines import LaneLinesAdapter
from as_platform.data.ingest.lane_mask import LaneMaskAdapter


class UnknownFormatError(ValueError):
    pass


ADAPTERS: tuple[IngestAdapter, ...] = (
    DmsYoloAdapter(),
    DmsCocoAdapter(),
    DmsInboxRawAdapter(),
    LaneMaskAdapter(),
    LaneLinesAdapter(),
)


def available_formats(project: str) -> list[str]:
    return [a.format_id for a in ADAPTERS if project in a.projects]


def detect_adapter(ctx: IngestContext) -> IngestAdapter:
    for adapter in ADAPTERS:
        if ctx.project not in adapter.projects:
            continue
        if adapter.can_handle(ctx):
            return adapter
    hint = ""
    if ctx.project == "dms":
        hint = (
            "；DMS 送标/inbox 请使用批次根目录，且至少包含 images/train/*.jpg"
            "（或已标注的 images/+labels/、COCO annotations/）"
        )
    raise UnknownFormatError(
        f"unable to detect format for project={ctx.project}, task={ctx.task}, "
        f"source={ctx.source_path}. supported={available_formats(ctx.project)}{hint}"
    )


def inspect_uploaded_dataset(project: str, task: str | None, source_path: str | Path) -> NormalizedDataset:
    ctx = IngestContext(project=project, task=task, source_path=Path(source_path).resolve())
    if not ctx.source_path.exists():
        raise FileNotFoundError(f"source path not found: {ctx.source_path}")
    adapter = detect_adapter(ctx)
    out = adapter.inspect(ctx)
    # Ensure adapter id is always reflected in output.
    out.format_id = adapter.format_id
    return out

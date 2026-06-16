"""Pack promote adapter registry."""
from __future__ import annotations

from as_platform.data.promote.adas_cuboid import AdasCuboidPromoteAdapter
from as_platform.data.promote.base import PackPromoteAdapter
from as_platform.data.promote.dms_yolo import DmsYoloPromoteAdapter

ADAPTERS: tuple[PackPromoteAdapter, ...] = (
    DmsYoloPromoteAdapter(),
    AdasCuboidPromoteAdapter(),
)


def get_promote_adapter(project: str) -> PackPromoteAdapter:
    for adapter in ADAPTERS:
        if adapter.project == project:
            return adapter
    raise ValueError(f"no promote adapter for project={project}")

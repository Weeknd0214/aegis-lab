"""Data ingest adapter base abstractions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IngestContext:
    project: str
    task: str | None
    source_path: Path


@dataclass
class NormalizedDataset:
    format_id: str
    project: str
    task: str | None
    source_path: str
    split_counts: dict[str, int] = field(default_factory=dict)
    sample_count: int = 0
    annotation_count: int = 0
    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IngestAdapter(ABC):
    """Adapter interface for task-specific upload formats."""

    format_id: str = "unknown"
    projects: tuple[str, ...] = ()

    @abstractmethod
    def can_handle(self, ctx: IngestContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(self, ctx: IngestContext) -> NormalizedDataset:
        raise NotImplementedError

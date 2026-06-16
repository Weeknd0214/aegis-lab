"""Pack promote adapter base types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PromoteContext:
    project: str
    task: str
    batch: str
    pack: str
    batch_dir: Path
    project_root: Path
    dry_run: bool = False
    skip_validate: bool = False
    allow_partial_3d: bool = False
    refresh: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromoteResult:
    ok: bool
    project: str
    task: str
    batch: str
    pack: str
    dest_path: str = ""
    images: int = 0
    labels: int = 0
    manifest_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stage: str = "ingested"
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["ok"] = self.ok
        return out


class PackPromoteAdapter(ABC):
    project: str = ""

    @abstractmethod
    def promote(self, ctx: PromoteContext) -> PromoteResult:
        raise NotImplementedError

    @abstractmethod
    def validate(self, ctx: PromoteContext) -> list[str]:
        """Return list of error messages; empty means pass."""
        raise NotImplementedError

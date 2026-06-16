"""DMS YOLO pack promote adapter."""
from __future__ import annotations

import sys
from pathlib import Path

from as_platform.data.promote.base import PackPromoteAdapter, PromoteContext, PromoteResult
from as_platform.data.promote.manifest import refresh_dms_yaml
from as_platform.data.promote.validate.dms_yolo import validate_dms_inbox_batch

_DMS_SCRIPTS = Path(__file__).resolve().parents[4] / "datasets" / "dms" / "scripts"
if str(_DMS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DMS_SCRIPTS))


def _resolve_promote_pack_dir(project_root: Path, pack: str) -> Path:
    """解析 pack 目录；损坏的 workspace 软链则回退为 HSAP 内真实目录。"""
    candidate = project_root / "packs" / pack
    if candidate.is_symlink():
        try:
            resolved = candidate.resolve()
            if resolved.is_dir():
                return resolved
        except OSError:
            pass
        candidate.unlink()
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


class DmsYoloPromoteAdapter(PackPromoteAdapter):
    project = "dms"

    def validate(self, ctx: PromoteContext) -> list[str]:
        if ctx.skip_validate:
            return []
        return validate_dms_inbox_batch(ctx.batch_dir)

    def promote(self, ctx: PromoteContext) -> PromoteResult:
        from ingest_incremental import promote_inbox_batch

        if not ctx.batch_dir.is_dir():
            return PromoteResult(
                ok=False,
                project=ctx.project,
                task=ctx.task,
                batch=ctx.batch,
                pack=ctx.pack,
                warnings=[f"batch_dir missing: {ctx.batch_dir}"],
            )

        pack_dir = _resolve_promote_pack_dir(ctx.project_root, ctx.pack)

        detail = promote_inbox_batch(
            root=ctx.project_root,
            task=ctx.task,
            pack=ctx.pack,
            src=ctx.batch_dir,
            mode=ctx.extra.get("mode"),
            dry_run=ctx.dry_run,
            refresh=ctx.refresh and not ctx.dry_run,
        )
        if ctx.refresh and not ctx.dry_run:
            refresh_dms_yaml(task=ctx.task)

        added = int(detail.get("added") or 0)
        return PromoteResult(
            ok=True,
            project=ctx.project,
            task=ctx.task,
            batch=ctx.batch,
            pack=ctx.pack,
            dest_path=str(ctx.project_root / "packs" / ctx.pack),
            labels=added,
            detail=detail,
        )

"""DMS YOLO pack promote adapter."""
from __future__ import annotations

import sys
from pathlib import Path

from as_platform.data.promote.base import PackPromoteAdapter, PromoteContext, PromoteResult
from as_platform.data.promote.manifest import refresh_dms_yaml
from as_platform.data.promote.validate.dms_yolo import validate_dms_task

_DMS_SCRIPTS = Path(__file__).resolve().parents[4] / "datasets" / "dms" / "scripts"
if str(_DMS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DMS_SCRIPTS))


class DmsYoloPromoteAdapter(PackPromoteAdapter):
    project = "dms"

    def validate(self, ctx: PromoteContext) -> list[str]:
        if ctx.skip_validate:
            return []
        return validate_dms_task(ctx.task)

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

        pack_dir = ctx.project_root / "packs" / ctx.pack
        pack_dir.mkdir(parents=True, exist_ok=True)

        detail = promote_inbox_batch(
            root=ctx.project_root,
            task=ctx.task,
            pack=ctx.pack,
            src=ctx.batch_dir,
            mode=ctx.extra.get("mode"),
            dry_run=ctx.dry_run,
            refresh=ctx.refresh and not ctx.dry_run,
        )
        if ctx.refresh and not ctx.dry_run and not ctx.skip_validate:
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

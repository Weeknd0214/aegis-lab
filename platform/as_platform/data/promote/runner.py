"""Unified pack promote entrypoint."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from as_platform.data.batch import read_meta, write_meta
from as_platform.data.catalog_cache import invalidate_catalog_cache
from as_platform.data.core import load_wf, proj_root
from as_platform.data.promote.base import PromoteContext, PromoteResult
from as_platform.data.promote.registry import get_promote_adapter
from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign
from as_platform.jobs.runner import _auto_snapshot
from as_platform.labeling.annotate import resolve_campaign_batch_dir


def _resolve_batch_dir(
    project: str,
    task: str,
    batch: str,
    *,
    location: str = "inbox",
) -> Path:
    wf = load_wf()
    root = proj_root(wf, project)
    if location == "inbox":
        if project == "adas":
            return (root / "inbox" / task / batch).resolve()
        return (root / "inbox" / task / batch).resolve()
    raise ValueError(f"unsupported location: {location}")


def _update_campaign_ingested(project: str, task: str, batch: str) -> None:
    try:
        with session_scope() as db:
            camp = (
                db.query(LabelingCampaign)
                .filter(
                    LabelingCampaign.project == project,
                    LabelingCampaign.task == task,
                    LabelingCampaign.batch == batch,
                )
                .order_by(LabelingCampaign.created_at.desc())
                .first()
            )
            if camp:
                camp.status = "ingested"
                db.flush()
                try:
                    batch_dir = resolve_campaign_batch_dir(camp)
                    meta = read_meta(batch_dir) or {}
                    meta["stage"] = "ingested"
                    meta["pipeline_version"] = 2
                    write_meta(batch_dir, meta)
                except Exception:
                    pass
    except Exception:
        pass


def promote_batch(
    project: str,
    *,
    task: str,
    batch: str | None = None,
    pack: str | None = None,
    batch_dir: Path | str | None = None,
    dry_run: bool = False,
    skip_validate: bool = False,
    allow_partial_3d: bool = False,
    refresh: bool = True,
    all_sources: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promote inbox batch into training pack (SDK entry)."""
    wf = load_wf()
    pcfg = wf["projects"][project]
    pack_name = pack or pcfg.get("base_pack")
    if not pack_name:
        raise ValueError(f"project {project} missing pack")
    if not task:
        raise ValueError("task required")
    if all_sources:
        raise ValueError("all_sources promote not yet in SDK; use CLI ingest_incremental")
    if not batch:
        raise ValueError("batch required")

    root = proj_root(wf, project)
    bdir = Path(batch_dir).resolve() if batch_dir else _resolve_batch_dir(project, task, batch)
    if not bdir.is_dir():
        raise ValueError(f"batch_dir not found: {bdir}")

    adapter = get_promote_adapter(project)
    ctx = PromoteContext(
        project=project,
        task=task,
        batch=batch,
        pack=pack_name,
        batch_dir=bdir,
        project_root=root,
        dry_run=dry_run,
        skip_validate=skip_validate,
        allow_partial_3d=allow_partial_3d,
        refresh=refresh,
        extra=extra or {},
    )

    val_errors = adapter.validate(ctx)
    if val_errors:
        raise ValueError("; ".join(val_errors))

    result: PromoteResult = adapter.promote(ctx)
    if not result.ok:
        raise ValueError(result.warnings[0] if result.warnings else "promote failed")

    if not dry_run:
        _update_campaign_ingested(project, task, batch)
        invalidate_catalog_cache()
        if project == "dms":
            _auto_snapshot("dms", task=task)

    out = result.to_dict()
    out["stdout"] = __import__("json").dumps(out, ensure_ascii=False)
    out["stderr"] = ""
    return out

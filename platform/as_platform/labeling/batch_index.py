"""批次索引：扫盘结果落库，列表页只查 DB（<200ms）。"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from as_platform.data.core import get_pending_report, load_wf
from as_platform.db.engine import session_scope
from as_platform.db.models import BatchIndex, LabelingCampaign
from as_platform.labeling.scope import enrich_batch_labels, load_dms_registry
from as_platform.labeling.stage import STAGE_ALIASES, effective_stage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def campaign_id_for_row(project: str, task: str, mode: str | None, batch: str, location: str) -> str:
    from as_platform.labeling.service import _campaign_id

    return _campaign_id(project, task, mode, batch, location)


def _batch_dict_to_fields(b: dict[str, Any], reg: dict) -> dict[str, Any] | None:
    if b.get("registry_only") and not b.get("batch"):
        return None
    row = enrich_batch_labels(b, reg)
    if row.get("registry_only"):
        pass
    raw_stage = row.get("stage")
    eff = effective_stage(raw_stage) or raw_stage or "raw_pool"
    allowed = (
        "raw_pool", "out_for_labeling", "returned", "labeling_submitted",
        "in_review", "review_approved", "review_rejected", "ingested",
    )
    if eff not in allowed and raw_stage not in allowed:
        return None
    project = row.get("project") or "dms"
    task = row.get("task") or ""
    mode = row.get("mode")
    batch = row.get("batch") or ""
    location = row.get("location") or "inbox"
    counts = row.get("counts") or {}
    cid = campaign_id_for_row(project, task, mode, batch, location)
    return {
        "campaign_id": cid,
        "project": project,
        "task": task or None,
        "mode": mode,
        "batch": batch,
        "pack": row.get("pack"),
        "location": location,
        "stage": eff,
        "batch_path": row.get("path"),
        "scope_key": row.get("scope_key"),
        "engineer": row.get("engineer"),
        "format": row.get("format"),
        "image_count": int(counts.get("images") or 0),
        "label_count": int(counts.get("labels") or 0),
        "has_meta": bool(row.get("has_meta")),
        "registry_only": bool(row.get("registry_only")),
        "next_cli": row.get("next_cli"),
        "domain": row.get("domain"),
        "domain_label": row.get("domain_label"),
        "task_label": row.get("task_label"),
        "mode_label": row.get("mode_label"),
        "labeling_profile": row.get("labeling_profile"),
        "export_default": row.get("export_default"),
        "ml_adapter": row.get("ml_adapter"),
        "indexed_at": _utcnow(),
    }


def upsert_batch_dict(b: dict[str, Any], *, reg: dict | None = None) -> str | None:
    """登记/单批更新时写入索引。"""
    reg = reg or load_dms_registry()
    fields = _batch_dict_to_fields(b, reg)
    if not fields:
        return None
    cid = fields["campaign_id"]
    fields["archived"] = False
    with session_scope() as db:
        rec = db.get(BatchIndex, cid)
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)
        else:
            db.add(BatchIndex(**fields))
        db.commit()
    return cid


def archive_batch(campaign_id: str) -> dict[str, Any]:
    """软删除：仅从工作台隐藏，不删磁盘数据。"""
    with session_scope() as db:
        rec = db.get(BatchIndex, campaign_id)
        if not rec:
            raise FileNotFoundError(campaign_id)
        if rec.archived:
            return {"ok": True, "campaign_id": campaign_id, "already_archived": True}
        if rec.stage != "raw_pool":
            raise ValueError("仅「待送标」批次可移除")
        camp = db.get(LabelingCampaign, campaign_id)
        if camp and camp.status not in ("not_opened", ""):
            raise ValueError("已开标的批次不可移除，请先在标注进度中处理")
        rec.archived = True
        rec.indexed_at = _utcnow()
        db.commit()
    return {"ok": True, "campaign_id": campaign_id}


def sync_index_stage(campaign_id: str, stage: str) -> None:
    eff = effective_stage(stage) or stage
    with session_scope() as db:
        rec = db.get(BatchIndex, campaign_id)
        if rec:
            rec.stage = eff
            rec.indexed_at = _utcnow()
            db.commit()


def index_count() -> int:
    with session_scope() as db:
        return db.query(BatchIndex).count()


def index_is_empty() -> bool:
    return index_count() == 0


def get_batch_by_campaign_id(campaign_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        rec = db.get(BatchIndex, campaign_id)
        return rec.to_list_row() if rec else None


def rebuild_batch_index(wf: dict | None = None) -> dict[str, Any]:
    """全量扫盘并重建索引（刷新/首次加载/登记后批量同步）。"""
    from as_platform.labeling.service import _registry_fallback_batches

    t0 = time.perf_counter()
    wf = wf or load_wf()
    reg = load_dms_registry()
    report = get_pending_report(wf)
    candidates: list[dict[str, Any]] = list(report.get("batches") or [])
    candidates.extend(_registry_fallback_batches(wf, reg))

    seen: set[str] = set()
    upserted = 0
    with session_scope() as db:
        for b in candidates:
            fields = _batch_dict_to_fields(b, reg)
            if not fields:
                continue
            cid = fields["campaign_id"]
            seen.add(cid)
            rec = db.get(BatchIndex, cid)
            if rec and rec.archived:
                continue
            if rec:
                for k, v in fields.items():
                    setattr(rec, k, v)
            else:
                db.add(BatchIndex(**fields))
            upserted += 1

        if seen:
            db.query(BatchIndex).filter(
                BatchIndex.campaign_id.notin_(seen),
                BatchIndex.archived.is_(False),
            ).delete(synchronize_session=False)
        db.commit()

    elapsed_ms = round((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "count": upserted,
        "elapsed_ms": elapsed_ms,
        "updated_at": report.get("updated_at"),
    }


def _expand_stage_filters_for_sql(stage_filters: list[str]) -> list[str]:
    """将筛选阶段展开为索引表中的实际 stage 值（含 review_approved 等别名）。"""
    expanded: set[str] = set()
    for sf in stage_filters:
        expanded.add(sf)
        for alias, canonical in STAGE_ALIASES.items():
            if canonical == sf:
                expanded.add(alias)
    return list(expanded)


def _index_query(db, *, stage_filters: list[str], q: str | None):
    from sqlalchemy import func, or_

    from as_platform.config import IS_POSTGRES

    query = db.query(BatchIndex).filter(
        BatchIndex.registry_only.is_(False),
        BatchIndex.archived.is_(False),
    )
    if stage_filters:
        query = query.filter(BatchIndex.stage.in_(_expand_stage_filters_for_sql(stage_filters)))
    text = (q or "").strip()
    if text:
        pattern = f"%{text}%"
        if IS_POSTGRES:
            query = query.filter(
                or_(
                    BatchIndex.batch.ilike(pattern),
                    BatchIndex.task.ilike(pattern),
                    BatchIndex.project.ilike(pattern),
                )
            )
        else:
            lp = pattern.lower()
            query = query.filter(
                or_(
                    func.lower(BatchIndex.batch).like(lp),
                    func.lower(func.coalesce(BatchIndex.task, "")).like(lp),
                    func.lower(BatchIndex.project).like(lp),
                )
            )
    return query


def list_batches_from_index(
    *,
    stage: str | None = None,
    stages: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
    q: str | None = None,
) -> dict[str, Any]:
    stage_filters = [s.strip() for s in (stages or []) if s and s.strip()]
    if stage and stage not in stage_filters:
        stage_filters.append(stage)

    with session_scope() as db:
        base = _index_query(db, stage_filters=stage_filters, q=q)
        total = base.count()
        recs = (
            base.order_by(BatchIndex.indexed_at.desc())
            .offset(max(0, offset))
            .limit(max(1, limit))
            .all()
        )
        page = [rec.to_list_row() for rec in recs]
        latest_indexed = max((rec.indexed_at for rec in recs), default=None)

    cids = [r["campaign_id"] for r in page if r.get("campaign_id")]

    camp_map: dict[str, dict[str, Any]] = {}
    if cids:
        with session_scope() as db:
            camps = db.query(LabelingCampaign).filter(LabelingCampaign.id.in_(cids)).all()
            for c in camps:
                camp_map[c.id] = {
                    "status": c.status,
                    "assigned_to_user_id": c.assigned_to_user_id,
                    "assigned_to_name": c.assigned_to_name,
                }

    progress_stages = frozenset({"out_for_labeling", "in_progress"})
    out: list[dict[str, Any]] = []
    for row in page:
        cid = row.get("campaign_id")
        camp = camp_map.get(cid) if cid else None
        status = camp["status"] if camp else "not_opened"
        if camp:
            row["assigned_to_user_id"] = camp["assigned_to_user_id"]
            row["assigned_to_name"] = camp["assigned_to_name"]
        row["campaign_status"] = status
        eff_stage = row.get("stage") or ""
        if camp and (status in progress_stages or eff_stage in progress_stages):
            try:
                from as_platform.labeling.progress import campaign_progress_summary

                row.update(campaign_progress_summary(cid))
            except Exception:
                row.update({"total_tasks": 0, "completed_tasks": 0, "assigned_tasks": 0})
        out.append(row)

    updated_at = latest_indexed.isoformat() if latest_indexed else None
    return {
        "items": out,
        "total": total,
        "offset": offset,
        "limit": limit,
        "updated_at": updated_at,
        "source": "index",
    }

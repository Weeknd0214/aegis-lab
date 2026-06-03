"""Campaign 与 pending 批次合并列表。"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from as_platform.config import WORKSPACE
from as_platform.data.core import get_pending_report, load_wf
from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign, LabelingExportJob, User
from as_platform.jobs.queue import enqueue_job, get_job
from as_platform.labeling.annotate import resolve_editor_xml, sync_campaign_config_xml
from as_platform.labeling.batch_stage import (
    on_labeling_export_job_succeeded,
    update_campaign_batch_meta_stage,
)
from as_platform.labeling.scope import (
    enrich_batch_labels,
    format_scope_key,
    load_dms_registry,
    load_labeling_registry,
)


def _campaign_id(project: str, task: str, mode: str | None, batch: str, location: str) -> str:
    sk = format_scope_key(project, task, mode)
    raw = f"{sk}:{batch}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _parse_scope_key(scope_key: str) -> tuple[str, str, str | None]:
    parts = scope_key.split(":")
    if parts[0] == "lane":
        return "lane", parts[1] if len(parts) > 1 else "lane_v1", None
    if len(parts) >= 3:
        return "dms", parts[1], parts[2]
    if len(parts) == 2:
        return "dms", parts[1], None
    return "dms", parts[-1], None


def _registry_fallback_batches(wf: dict, reg: dict) -> list[dict[str, Any]]:
    """labeling.registry 中有配置但 pending 未扫到的批次（如空 inbox）。"""
    from pathlib import Path

    from as_platform.data.batch import enrich_batch
    from as_platform.data.core import proj_root

    profiles = load_labeling_registry().get("profiles") or {}
    rows: list[dict[str, Any]] = []
    dms_root = proj_root(wf, "dms")
    for _pk, prof in profiles.items():
        scope_key = prof.get("scope_key") or ""
        project, task, mode = _parse_scope_key(scope_key)
        if project != "dms":
            continue
        batch = mode or task
        batch_dir = None
        if mode:
            try:
                import sys

                scripts = WORKSPACE / "datasets" / "dms" / "scripts"
                if str(scripts) not in sys.path:
                    sys.path.insert(0, str(scripts))
                from task_registry import inbox_dir, resolve_task_id

                task_r, mode_r = resolve_task_id(task, mode)
                batch_dir = inbox_dir(dms_root, task_r, mode_r, reg)
            except Exception:
                batch_dir = dms_root / "inbox" / task / mode
        else:
            batch_dir = dms_root / "inbox" / task / batch
        if not isinstance(batch_dir, Path) or not batch_dir.is_dir():
            row = {
                "project": project,
                "task": task,
                "mode": mode,
                "batch": batch,
                "stage": "raw_pool",
                "location": "inbox",
                "path": str(batch_dir) if batch_dir else "",
                "counts": {"images": 0, "labels": 0},
                "registry_only": True,
            }
        else:
            row = enrich_batch(
                batch_dir,
                project=project,
                task=task,
                pack=None,
                batch=batch,
                location="inbox",
            )
            row["mode"] = mode
        row["scope_key"] = scope_key
        rows.append(row)
    return rows


def list_labeling_batches(
    *,
    stage: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    wf = load_wf()
    report = get_pending_report(wf)
    reg = load_dms_registry()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_stages = ("raw_pool", "out_for_labeling", "returned", "labeling_submitted", "in_review", "review_approved", "review_rejected")

    def _append(b: dict[str, Any]) -> None:
        if stage and b.get("stage") != stage:
            return
        if b.get("stage") not in allowed_stages:
            return
        row = enrich_batch_labels(b, reg)
        cid = _campaign_id(
            row["project"], row.get("task") or "", row.get("mode"), row["batch"], row.get("location") or "inbox"
        )
        key = f"{cid}"
        if key in seen:
            return
        seen.add(key)
        with session_scope() as db:
            camp = db.get(LabelingCampaign, cid)
            status = camp.status if camp else "not_opened"
            if camp:
                row["assigned_to_user_id"] = camp.assigned_to_user_id
                row["assigned_to_name"] = camp.assigned_to_name
        row["campaign_id"] = cid
        row["campaign_status"] = status
        if camp and status in ("in_progress", "labeling_submitted"):
            try:
                from as_platform.labeling.progress import campaign_progress_summary

                row.update(campaign_progress_summary(cid))
            except Exception:
                row.update({"total_tasks": 0, "completed_tasks": 0, "assigned_tasks": 0})
        items.append(row)

    for b in report.get("batches", []):
        _append(b)

    for b in _registry_fallback_batches(wf, reg):
        _append(b)

    total = len(items)
    page = items[max(0, offset) : max(0, offset) + max(1, limit)]
    return {
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "updated_at": report.get("updated_at"),
    }


def open_campaign(
    *,
    project: str,
    task: str,
    batch: str,
    mode: str | None = None,
    pack: str | None = None,
    location: str = "inbox",
) -> dict[str, Any]:
    cid = _campaign_id(project, task, mode, batch, location)
    config_xml = resolve_editor_xml(project, task, mode)
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        camp = db.get(LabelingCampaign, cid)
        if not camp:
            camp = LabelingCampaign(
                id=cid,
                project=project,
                task=task,
                mode=mode,
                batch=batch,
                pack=pack,
                location=location,
                status="in_progress",
                config_xml=config_xml,
                created_at=now,
                updated_at=now,
            )
            db.add(camp)
        else:
            camp.status = "in_progress"
            camp.updated_at = now
            sync_campaign_config_xml(camp)
        db.flush()
        out = camp.to_dict()
        out["config_xml"] = camp.config_xml
        update_campaign_batch_meta_stage(camp, "out_for_labeling")
    reg = load_dms_registry() if project == "dms" else None
    row = enrich_batch_labels(out, reg)
    row["stage"] = "out_for_labeling"
    return row


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return None
        row = camp.to_dict()
        row["config_xml"] = camp.config_xml
    reg = load_dms_registry() if row.get("project") == "dms" else None
    return enrich_batch_labels(row, reg)


def _export_job_id() -> str:
    return f"lej-{uuid.uuid4().hex[:16]}"


def _record_export_job(campaign_id: str, action: str, job: dict[str, Any]) -> dict[str, Any]:
    ej_id = _export_job_id()
    job_id = job.get("id")
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        ej = LabelingExportJob(
            id=ej_id,
            campaign_id=campaign_id,
            action=action,
            job_id=job_id,
            status=job.get("status") or "queued",
            created_at=now,
        )
        db.add(ej)
    out = get_export_job(ej_id)
    return out or {"id": ej_id, "campaign_id": campaign_id, "action": action, "job_id": job_id}


def _sync_export_job_from_queue(ej: LabelingExportJob) -> None:
    if not ej.job_id:
        return
    job = get_job(ej.job_id)
    if not job:
        return
    ej.status = job.get("status") or ej.status
    if job.get("finished_at"):
        try:
            ej.finished_at = datetime.fromisoformat(str(job["finished_at"]).replace("Z", "+00:00"))
        except Exception:
            pass
    if job.get("result") is not None:
        ej.result_json = json.dumps(job.get("result"), ensure_ascii=False)
    if ej.action == "labeling_export" and ej.status in ("succeeded", "completed"):
        on_labeling_export_job_succeeded(
            {"action": "labeling_export", "params": {"campaign_id": ej.campaign_id}}
        )


def get_export_job(export_job_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        ej = db.get(LabelingExportJob, export_job_id)
        if not ej:
            return None
        _sync_export_job_from_queue(ej)
        db.flush()
        return ej.to_dict()


def list_campaign_export_jobs(campaign_id: str, *, limit: int = 30) -> dict[str, Any]:
    with session_scope() as db:
        rows = (
            db.query(LabelingExportJob)
            .filter_by(campaign_id=campaign_id)
            .filter(LabelingExportJob.action != "labeling_ml_predict")
            .order_by(LabelingExportJob.created_at.desc())
            .limit(limit)
            .all()
        )
        for ej in rows:
            _sync_export_job_from_queue(ej)
        db.flush()
        items = [ej.to_dict() for ej in rows]
    return {"items": items, "campaign_id": campaign_id}


def list_labeling_assignees() -> dict[str, Any]:
    """可指派为批次负责人的用户（标注相关角色）。"""
    role_codes = ("labeler", "internal_labeler", "vendor_labeler", "engineer", "admin")
    with session_scope() as db:
        users = (
            db.query(User)
            .filter(User.is_active.is_(True))
            .order_by(User.name)
            .all()
        )
        items = []
        for u in users:
            codes = {r.code for r in (u.roles or [])}
            if codes.intersection(role_codes):
                items.append({"id": u.id, "name": u.name or f"user-{u.id}", "roles": sorted(codes)})
    return {"items": items}


def _find_batch_for_campaign_id(campaign_id: str) -> dict[str, Any] | None:
    """由确定性 campaign_id 反查 pending / registry 批次行。"""
    wf = load_wf()
    reg = load_dms_registry()
    candidates: list[dict[str, Any]] = []
    report = get_pending_report(wf)
    candidates.extend(report.get("batches") or [])
    candidates.extend(_registry_fallback_batches(wf, reg))
    for b in candidates:
        cid = _campaign_id(
            b.get("project") or "dms",
            b.get("task") or "",
            b.get("mode"),
            b.get("batch") or "",
            b.get("location") or "inbox",
        )
        if cid == campaign_id:
            return b
    return None


def ensure_campaign_record(campaign_id: str) -> None:
    """提交/导出前保证 DB 中有 LabelingCampaign（未点「进入标注」时自动创建）。"""
    with session_scope() as db:
        if db.get(LabelingCampaign, campaign_id):
            return
    batch = _find_batch_for_campaign_id(campaign_id)
    if not batch:
        raise FileNotFoundError("campaign not found")
    if batch.get("registry_only"):
        raise ValueError("该条目为任务模板占位，无真实 inbox 批次目录，请先送标入湖或从「进入标注」开启真实批次")
    open_campaign(
        project=batch.get("project") or "dms",
        task=batch.get("task") or "",
        batch=batch["batch"],
        mode=batch.get("mode"),
        pack=batch.get("pack"),
        location=batch.get("location") or "inbox",
    )


def assign_campaign(campaign_id: str, user_id: int | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        if user_id is None:
            camp.assigned_to_user_id = None
            camp.assigned_to_name = None
        else:
            user = db.get(User, user_id)
            if not user:
                raise ValueError(f"用户不存在: {user_id}")
            camp.assigned_to_user_id = user_id
            camp.assigned_to_name = user.name
        camp.updated_at = now
        db.flush()
        out = camp.to_dict()
    reg = load_dms_registry() if out.get("project") == "dms" else None
    return enrich_batch_labels(out, reg)


def submit_campaign(campaign_id: str) -> dict[str, Any]:
    ensure_campaign_record(campaign_id)
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        camp.status = "in_review"
        camp.updated_at = now
        db.flush()
        out = camp.to_dict()
        update_campaign_batch_meta_stage(camp, "in_review")
    reg = load_dms_registry() if out.get("project") == "dms" else None
    row = enrich_batch_labels(out, reg)
    row["stage"] = "in_review"
    return row


def trigger_labeling_export(campaign_id: str) -> dict[str, Any]:
    row = get_campaign(campaign_id)
    if not row:
        raise FileNotFoundError("campaign not found")
    job = enqueue_job(
        "labeling_export",
        {
            "campaign_id": campaign_id,
            "export_default": row.get("export_default"),
            "scope_key": row.get("scope_key"),
            "batch": row.get("batch"),
        },
        async_run=True,
    )
    ej = _record_export_job(campaign_id, "labeling_export", job)
    return {"ok": True, "job": job, "export_job": ej, "export_default": row.get("export_default")}

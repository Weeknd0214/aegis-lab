"""批次送标申请 CRUD 与提交审批。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from as_platform.audit.queue import reject_approval, submit_approval
from as_platform.db.engine import session_scope
from as_platform.db.models import Approval, BatchDelivery, Job, User
from as_platform.integrations.delivery_ingest import validate_delivery_fields

EDITABLE_STATUSES = frozenset({"draft", "rejected", "ingest_failed"})
DELETABLE_STATUSES = frozenset({"draft", "rejected", "ingest_failed"})
RETRY_INGEST_STATUSES = frozenset({"ingest_failed", "ingesting"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_delivery_id() -> str:
    return f"del-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def _normalize_task(project: str, task: str | None) -> str | None:
    if project == "dms":
        return (task or "").strip() or None
    return None


def _enrich_delivery_dict(db, rec: BatchDelivery) -> dict[str, Any]:
    d = rec.to_dict()
    d["submitted_by"] = rec.submitted_by_name
    if rec.approval_id:
        ap = db.get(Approval, rec.approval_id)
        if ap:
            d["approval_status"] = ap.status
            d["job_id"] = ap.job_id
            if ap.job_id:
                job = db.get(Job, ap.job_id)
                if job:
                    d["job_status"] = job.status
    return d


def list_deliveries(
    *,
    status: str | None = None,
    mine_user_id: int | None = None,
    mine_editable_only: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    with session_scope() as db:
        q = db.query(BatchDelivery).order_by(BatchDelivery.updated_at.desc())
        if status:
            q = q.filter(BatchDelivery.status == status)
        if mine_user_id is not None:
            q = q.filter(
                (BatchDelivery.owner_user_id == mine_user_id)
                | (BatchDelivery.submitted_by_user_id == mine_user_id)
            )
        if mine_editable_only:
            q = q.filter(BatchDelivery.status.in_(("draft", "rejected", "ingest_failed")))
        total = q.count()
        rows = q.offset(max(0, offset)).limit(max(1, limit)).all()
        return {
            "items": [_enrich_delivery_dict(db, r) for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
            "count": len(rows),
        }


def get_delivery(delivery_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        return _enrich_delivery_dict(db, rec) if rec else None


def create_delivery(data: dict[str, Any], user: User) -> dict[str, Any]:
    project = (data.get("project") or "dms").strip()
    task = _normalize_task(project, data.get("task"))
    mode = (data.get("mode") or "").strip() or None
    batch_name = (data.get("batch_name") or "").strip()
    data_path = (data.get("data_path") or "").strip()

    if not batch_name:
        raise ValueError("批次名必填")
    if data_path:
        err = validate_delivery_fields(
            project=project,
            task=task,
            mode=mode,
            batch_name=batch_name,
            data_path=data_path,
        )
        if err:
            raise ValueError(err)

    with session_scope() as db:
        dup = (
            db.query(BatchDelivery)
            .filter_by(project=project, task=task, mode=mode, batch_name=batch_name)
            .filter(BatchDelivery.status.notin_(("rejected", "ingest_failed")))
            .first()
        )
        if dup:
            raise ValueError(f"已存在同批次申请: {dup.id} ({dup.status})")

        rec = BatchDelivery(
            id=_new_delivery_id(),
            project=project,
            task=task,
            mode=mode,
            batch_name=batch_name,
            source_type=(data.get("source_type") or "").strip() or None,
            vehicle_scene=(data.get("vehicle_scene") or "").strip() or None,
            collection_start=(data.get("collection_start") or "").strip() or None,
            collection_end=(data.get("collection_end") or "").strip() or None,
            data_path=data_path,
            estimated_count=int(data["estimated_count"]) if data.get("estimated_count") not in (None, "") else None,
            remark=(data.get("remark") or "").strip() or None,
            status="draft",
            owner_user_id=data.get("owner_user_id") or user.id,
            owner_name=(data.get("owner_name") or user.name),
            submitted_by_user_id=user.id,
            submitted_by_name=user.name,
        )
        db.add(rec)
        db.flush()
        return rec.to_dict()


def update_delivery(delivery_id: str, data: dict[str, Any], user: User) -> dict[str, Any]:
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if not rec:
            raise ValueError("送标申请不存在")
        if rec.status not in EDITABLE_STATUSES:
            raise ValueError(f"当前状态不可编辑: {rec.status}")

        project = (data.get("project") or rec.project).strip()
        task = _normalize_task(project, data.get("task") if "task" in data else rec.task)
        mode = (data.get("mode") if "mode" in data else rec.mode) or None
        if mode:
            mode = mode.strip() or None
        batch_name = (data.get("batch_name") or rec.batch_name).strip()
        data_path = (data.get("data_path") or rec.data_path).strip()

        err = validate_delivery_fields(
            project=project,
            task=task,
            mode=mode,
            batch_name=batch_name,
            data_path=data_path,
        )
        if err:
            raise ValueError(err)

        rec.project = project
        rec.task = task
        rec.mode = mode
        rec.batch_name = batch_name
        rec.data_path = data_path
        if "source_type" in data:
            rec.source_type = (data.get("source_type") or "").strip() or None
        if "vehicle_scene" in data:
            rec.vehicle_scene = (data.get("vehicle_scene") or "").strip() or None
        if "collection_start" in data:
            rec.collection_start = (data.get("collection_start") or "").strip() or None
        if "collection_end" in data:
            rec.collection_end = (data.get("collection_end") or "").strip() or None
        if "estimated_count" in data:
            v = data.get("estimated_count")
            rec.estimated_count = int(v) if v not in (None, "") else None
        if "remark" in data:
            rec.remark = (data.get("remark") or "").strip() or None
        if "owner_user_id" in data:
            rec.owner_user_id = data.get("owner_user_id") or rec.owner_user_id
        if "owner_name" in data:
            rec.owner_name = (data.get("owner_name") or "").strip() or rec.owner_name
        if rec.status in ("rejected", "ingest_failed"):
            rec.status = "draft"
            rec.error_message = None
        rec.updated_at = _utcnow()
        db.flush()
        return rec.to_dict()


def submit_delivery_for_review(delivery_id: str, user: User) -> dict[str, Any]:
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if not rec:
            raise ValueError("送标申请不存在")
        if rec.status not in EDITABLE_STATUSES:
            raise ValueError(f"当前状态不可提交: {rec.status}")

        err = validate_delivery_fields(
            project=rec.project,
            task=rec.task,
            mode=rec.mode,
            batch_name=rec.batch_name,
            data_path=rec.data_path,
        )
        if err:
            raise ValueError(err)

        params = {
            "delivery_id": rec.id,
            "project": rec.project,
            "task": rec.task,
            "mode": rec.mode,
            "batch_name": rec.batch_name,
            "data_path": rec.data_path,
            "source_type": rec.source_type,
            "vehicle_scene": rec.vehicle_scene,
            "estimated_count": rec.estimated_count,
            "remark": rec.remark,
        }
        approval = submit_approval(
            "delivery_ingest",
            params,
            submitted_by=user.name,
            submitted_by_user_id=user.id,
            note=f"数据送标入湖 {rec.batch_name}",
        )
        rec.status = "pending_review"
        rec.approval_id = approval.get("id")
        rec.submitted_by_user_id = user.id
        rec.submitted_by_name = user.name
        rec.updated_at = _utcnow()
        db.flush()
        out = rec.to_dict()
        out["approval"] = approval
        return out


def mark_delivery_rejected_by_approval(approval_id: str) -> None:
    with session_scope() as db:
        rec = db.query(BatchDelivery).filter_by(approval_id=approval_id).first()
        if rec and rec.status == "pending_review":
            rec.status = "rejected"
            rec.updated_at = _utcnow()
            db.flush()


def on_approval_rejected(approval_id: str, **_: Any) -> None:
    mark_delivery_rejected_by_approval(approval_id)


def mark_delivery_ingest_failed(delivery_id: str | None, approval_id: str | None, error: str) -> None:
    """Job 失败或入湖异常时，确保台账状态为 ingest_failed（避免卡在 ingesting）。"""
    msg = (error or "")[:2000]
    with session_scope() as db:
        rec = None
        if delivery_id:
            rec = db.get(BatchDelivery, delivery_id)
        if not rec and approval_id:
            rec = db.query(BatchDelivery).filter_by(approval_id=approval_id).first()
        if not rec:
            return
        if rec.status in ("ingesting", "pending_review"):
            rec.status = "ingest_failed"
            rec.error_message = msg
            rec.updated_at = _utcnow()
            db.flush()


def delete_delivery(delivery_id: str, user: User) -> None:
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if not rec:
            raise ValueError("送标申请不存在")
        if rec.status not in DELETABLE_STATUSES:
            raise ValueError(f"当前状态不可删除: {rec.status}")
        db.delete(rec)
        db.flush()


def retry_delivery_ingest(delivery_id: str, user: User) -> dict[str, Any]:
    """入湖失败后重新执行入湖 Job（无需重新走审核）。"""
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if not rec:
            raise ValueError("送标申请不存在")
        if rec.status not in RETRY_INGEST_STATUSES:
            raise ValueError(f"当前状态不可重新入湖: {rec.status}")
        err = validate_delivery_fields(
            project=rec.project,
            task=rec.task,
            mode=rec.mode,
            batch_name=rec.batch_name,
            data_path=rec.data_path,
        )
        if err:
            raise ValueError(err)
        approval_id = rec.approval_id
        rec.status = "ingesting"
        rec.error_message = None
        rec.updated_at = _utcnow()
        db.flush()

    from as_platform.jobs.queue import enqueue_job

    job = enqueue_job(
        "delivery_ingest",
        {"delivery_id": delivery_id},
        approval_id=approval_id,
        async_run=True,
    )
    return {"ok": True, "job_id": job.get("id"), "delivery_id": delivery_id}

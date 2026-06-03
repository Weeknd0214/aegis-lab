"""审核队列（SQLite）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from as_platform.db.engine import session_scope
from as_platform.db.models import Approval, User
from as_platform.config import LANE_DATA_VIZ_ENABLED
from as_platform.integrations.feishu_notify import send_chat_async

ACTIONS_REQUIRING_APPROVAL = {
    "build_dms", "build_lane", "enable_pack", "disable_pack",
    "train_dms", "train_lane", "eval_dms", "promote_dms",
    "pipeline_dms", "register_batch", "eval_lane", "visualize_dms", "visualize_lane",
    "delivery_ingest",
}

REJECTION_CATEGORIES = {
    "data_quality": "数据质量问题",
    "wrong_params": "参数配置有误",
    "duplicate": "重复提交",
    "not_needed": "无需此操作",
    "permission": "权限不足",
    "other": "其他原因",
}

REJECTION_CATEGORY_LABEL = {k: v for k, v in REJECTION_CATEGORIES.items()}


ACTION_LABELS = {
    "build_dms": "DMS 入库 (build)",
    "build_lane": "车道线合并列表 (build lane)",
    "enable_pack": "启用训练数据包",
    "disable_pack": "停用训练数据包",
    "train_dms": "DMS 训练",
    "train_lane": "车道线训练",
    "eval_dms": "DMS 评估",
    "eval_lane": "车道线评估",
    "visualize_dms": "DMS 检测可视化",
    "visualize_lane": "车道线可视化",
    "promote_dms": "DMS 模型晋级",
    "pipeline_dms": "DMS 半自动流水线",
    "register_batch": "登记批次元数据",
    "delivery_ingest": "数据送标入湖",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return f"apr-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def submit_approval(
    action: str,
    params: dict[str, Any],
    *,
    submitted_by: str | None = None,
    submitted_by_user_id: int | None = None,
    note: str | None = None,
    auto_execute: bool = False,
) -> dict[str, Any]:
    if action not in ACTIONS_REQUIRING_APPROVAL:
        raise ValueError(f"未知动作: {action}，允许: {sorted(ACTIONS_REQUIRING_APPROVAL)}")
    if action == "visualize_lane" and not LANE_DATA_VIZ_ENABLED:
        raise ValueError("车道线数据可视化暂未开放")

    from as_platform.agents.trace import trace_span

    with session_scope() as db:
        rec = Approval(
            id=_new_id(),
            status="pending",
            action=action,
            action_label=ACTION_LABELS.get(action, action),
            note=note,
            submitted_by_name=submitted_by,
            submitted_by_user_id=submitted_by_user_id,
            submitted_at=_now(),
        )
        rec.set_params(params)
        db.add(rec)
        db.flush()
        out = rec.to_dict()

    with trace_span("approval_submit", approval_id=out["id"], action=action):
        pass

    if auto_execute:
        return approve_and_execute(out["id"], reviewed_by="system", comment="auto_execute")

    # 飞书通知 + 审计日志
    label = ACTION_LABELS.get(action, action)
    send_chat_async(f"📋 新审核提交\n{label}\n提单人: {submitted_by or '—'}\n备注: {note or '—'}")
    from as_platform.audit.log_utils import log_op
    log_op(user_id=submitted_by_user_id, user_name=submitted_by or "", category="audit", action="submit_approval",
           target_type="approval", target_id=out["id"], summary=f"提交审核: {label}",
           detail={"action": action, "params": params, "note": note})

    return out


def list_approvals(
    status: str | None = None,
    *,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    with session_scope() as db:
        q = db.query(Approval).order_by(Approval.submitted_at.desc())
        if status:
            q = q.filter(Approval.status == status)
        total = q.count()
        rows = q.offset(max(0, offset)).limit(max(1, limit)).all()
        return {
            "items": [a.to_dict() for a in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


def get_approval(record_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        rec = db.get(Approval, record_id)
        return rec.to_dict() if rec else None


def _update(record_id: str, **patch: Any) -> dict[str, Any] | None:
    with session_scope() as db:
        rec = db.get(Approval, record_id)
        if not rec:
            return None
        for k, v in patch.items():
            if k == "result" and isinstance(v, dict):
                rec.set_result(v)
            elif hasattr(rec, k):
                setattr(rec, k, v)
        db.flush()
        return rec.to_dict()


def approve_and_execute(
    record_id: str,
    *,
    reviewed_by: str | None = None,
    reviewed_by_user_id: int | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    rec = get_approval(record_id)
    if not rec:
        raise ValueError(f"审核单不存在: {record_id}")
    if rec.get("status") != "pending":
        raise ValueError(f"当前状态不可审批: {rec.get('status')}")

    from as_platform.agents.trace import trace_span
    from as_platform.jobs.queue import enqueue_job

    _update(
        record_id,
        status="approved",
        reviewed_by_name=reviewed_by,
        reviewed_by_user_id=reviewed_by_user_id,
        reviewed_at=_now(),
        review_comment=comment,
    )

    with trace_span("approval_approved", approval_id=record_id, action=rec["action"]):
        job = enqueue_job(rec["action"], rec.get("params") or {}, approval_id=record_id, async_run=True)

    _update(record_id, job_id=job.get("id"), status="running")

    # 飞书通知 + 审计日志
    label = ACTION_LABELS.get(rec["action"], rec["action"])
    submitter = rec.get("submitted_by") or rec.get("submitted_by_name") or ""
    send_chat_async(f"✅ 审核通过\n{label}\n审核人: {reviewed_by or '—'}\n提单人: {submitter}")
    from as_platform.audit.log_utils import log_op
    log_op(user_id=reviewed_by_user_id, user_name=reviewed_by or "", category="audit", action="approve",
           target_type="approval", target_id=record_id, summary=f"审核通过: {label}",
           detail={"comment": comment})

    return get_approval(record_id) or {}


def reject_approval(
    record_id: str,
    *,
    reviewed_by: str | None = None,
    reviewed_by_user_id: int | None = None,
    comment: str | None = None,
    rejection_category: str = "",
) -> dict[str, Any]:
    rec = get_approval(record_id)
    if not rec:
        raise ValueError(f"审核单不存在: {record_id}")
    if rec.get("status") != "pending":
        raise ValueError(f"当前状态不可驳回: {rec.get('status')}")
    out = _update(
        record_id,
        status="rejected",
        reviewed_by_name=reviewed_by,
        reviewed_by_user_id=reviewed_by_user_id,
        reviewed_at=_now(),
        review_comment=comment,
        rejection_category=rejection_category or "",
    ) or {}
    # 飞书通知：审核驳回
    label = ACTION_LABELS.get(rec["action"], rec["action"])
    cat = REJECTION_CATEGORIES.get(rejection_category, rejection_category) if rejection_category else ""
    submitter = rec.get("submitted_by") or rec.get("submitted_by_name") or ""
    reason_text = f"\n原因: {cat}" if cat else ""
    send_chat_async(f"❌ 审核驳回\n{label}\n审核人: {reviewed_by or '—'}\n提单人: {submitter}{reason_text}\n意见: {comment or '—'}")
    from as_platform.audit.log_utils import log_op
    log_op(user_id=reviewed_by_user_id, user_name=reviewed_by or "", category="audit", action="reject",
           target_type="approval", target_id=record_id, summary=f"审核驳回: {label}",
           detail={"comment": comment, "rejection_category": rejection_category})

    try:
        from as_platform.deliveries.service import mark_delivery_rejected_by_approval
        mark_delivery_rejected_by_approval(record_id)
    except Exception:
        pass
    return out


def batch_approve(
    record_ids: list[str],
    *,
    reviewed_by: str | None = None,
    reviewed_by_user_id: int | None = None,
) -> dict[str, Any]:
    """批量通过审核。返回 {approved, failed, errors}。"""
    approved: list[str] = []
    errors: list[dict[str, str]] = []
    for rid in record_ids:
        try:
            approve_and_execute(rid, reviewed_by=reviewed_by, reviewed_by_user_id=reviewed_by_user_id)
            approved.append(rid)
        except Exception as e:
            errors.append({"id": rid, "error": str(e)})
    return {"approved": len(approved), "failed": len(errors), "errors": errors}


def batch_reject(
    record_ids: list[str],
    *,
    reviewed_by: str | None = None,
    reviewed_by_user_id: int | None = None,
    comment: str | None = None,
    rejection_category: str = "",
) -> dict[str, Any]:
    """批量驳回审核。"""
    rejected: list[str] = []
    errors: list[dict[str, str]] = []
    for rid in record_ids:
        try:
            reject_approval(rid, reviewed_by=reviewed_by, reviewed_by_user_id=reviewed_by_user_id,
                            comment=comment, rejection_category=rejection_category)
            rejected.append(rid)
        except Exception as e:
            errors.append({"id": rid, "error": str(e)})
    return {"rejected": len(rejected), "failed": len(errors), "errors": errors}

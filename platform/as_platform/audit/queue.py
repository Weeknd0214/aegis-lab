"""审核队列（SQLite）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from as_platform.db.engine import session_scope
from as_platform.db.models import Approval, User
from as_platform.config import LANE_DATA_VIZ_ENABLED

ACTIONS_REQUIRING_APPROVAL = {
    "build_dms", "build_lane", "enable_pack", "disable_pack",
    "train_dms", "train_lane", "eval_dms", "promote_dms",
    "pipeline_dms", "register_batch", "eval_lane", "visualize_dms", "visualize_lane",
}

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
    return out


def list_approvals(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as db:
        q = db.query(Approval).order_by(Approval.submitted_at.desc())
        if status:
            q = q.filter(Approval.status == status)
        return [a.to_dict() for a in q.limit(limit).all()]


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
    return get_approval(record_id) or {}


def reject_approval(
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
        raise ValueError(f"当前状态不可驳回: {rec.get('status')}")
    return _update(
        record_id,
        status="rejected",
        reviewed_by_name=reviewed_by,
        reviewed_by_user_id=reviewed_by_user_id,
        reviewed_at=_now(),
        review_comment=comment,
    ) or {}

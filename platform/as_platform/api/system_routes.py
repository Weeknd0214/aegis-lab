"""系统管理 API 路由 — 模块化前缀 /api/v1/system

本路由将 audit/jobs/traces/agents 功能以模块化路径重新暴露。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from as_platform.agents.tools import TOOL_REGISTRY, invoke_tool
from as_platform.agents.trace import get_trace, list_traces
from as_platform.audit.queue import (
    ACTION_LABELS,
    ACTIONS_REQUIRING_APPROVAL,
    REJECTION_CATEGORIES,
    approve_and_execute,
    batch_approve,
    batch_reject,
    get_approval,
    list_approvals,
    reject_approval,
    submit_approval,
)
from as_platform.audit.preview import find_image_ref, list_scope_images, resolve_approval_scope
from as_platform.auth.deps import can_submit_action, get_current_user, require_any_permission, require_permission
from as_platform.auth.feishu import sync_feishu_users_to_db
from as_platform.auth.users import list_users, list_users_paginated, set_user_roles
from as_platform.db.engine import get_db
from as_platform.db.init_db import user_to_dict
from as_platform.db.models import User
from as_platform.jobs.queue import enqueue_job, get_job, list_jobs

router = APIRouter(prefix="/api/v1/system", tags=["system"])


# ── Audit / Approvals ──

@router.get("/audit")
def api_system_approvals(
    _user: Annotated[User, Depends(require_permission("read:audit"))],
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_approvals(status=status, offset=offset, limit=limit)


@router.get("/audit/actions")
def api_system_actions(_user: Annotated[User, Depends(require_permission("read:audit"))]) -> dict[str, Any]:
    return {"actions": [{"id": k, "label": ACTION_LABELS.get(k, k)} for k in sorted(ACTIONS_REQUIRING_APPROVAL)]}


class SubmitApprovalBody(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class ReviewBody(BaseModel):
    comment: str | None = None


class RejectBody(BaseModel):
    comment: str | None = None
    rejection_category: str = ""


class BatchReviewBody(BaseModel):
    ids: list[str] = Field(default_factory=list)
    comment: str | None = None
    rejection_category: str = ""


@router.post("/audit/submit")
def api_system_submit_approval(
    body: SubmitApprovalBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    if not can_submit_action(user, body.action):
        raise HTTPException(403, f"无权提交: {body.action}")
    try:
        return submit_approval(
            body.action, body.params,
            submitted_by=user.name,
            submitted_by_user_id=user.id,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class BuildFromBatchBody(BaseModel):
    project: str = "dms"
    task: str
    batch: str
    pack: str = "dms_v2"
    location: str = "inbox"
    note: str | None = None


@router.post("/audit/submit-build-batch")
def api_system_submit_build_batch(
    body: BuildFromBatchBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    action = "build_adas" if body.project == "adas" else "build_dms"
    if not can_submit_action(user, action) and not can_submit_action(user, "build_dms"):
        raise HTTPException(403, "无权提交 build")
    pack = body.pack
    if body.project == "adas" and (not pack or pack == "dms_v2"):
        pack = "adas_moon3d_v1"
    params: dict[str, Any] = {
        "project": body.project,
        "task": body.task,
        "pack": pack,
    }
    if body.location == "inbox":
        params["batch"] = body.batch
    else:
        params["all_sources"] = True
    try:
        return submit_approval(
            action,
            params,
            submitted_by=user.name,
            submitted_by_user_id=user.id,
            note=body.note or f"入库 {body.batch}",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/audit/{record_id}")
def api_system_get_approval(
    record_id: str,
    _user: Annotated[User, Depends(require_permission("read:audit"))],
) -> dict[str, Any]:
    rec = get_approval(record_id)
    if not rec:
        raise HTTPException(404, "审核单不存在")
    return rec


@router.get("/audit/{record_id}/preview")
def api_system_approval_preview(
    record_id: str,
    _user: Annotated[User, Depends(require_permission("read:audit"))],
) -> dict[str, Any]:
    rec = get_approval(record_id)
    if not rec:
        raise HTTPException(404, "审核单不存在")
    try:
        scope = resolve_approval_scope(rec["action"], rec.get("params") or {})
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "approval": rec,
        "scope_label": scope.get("scope_label"),
        "task": scope.get("task"),
        "pack": scope.get("pack"),
        "class_names": scope.get("class_names"),
    }


@router.get("/audit/{record_id}/images")
def api_system_approval_images(
    record_id: str,
    _user: Annotated[User, Depends(require_permission("read:audit"))],
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
) -> dict[str, Any]:
    rec = get_approval(record_id)
    if not rec:
        raise HTTPException(404, "审核单不存在")
    try:
        scope = resolve_approval_scope(rec["action"], rec.get("params") or {})
        return list_scope_images(scope, offset=offset, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/audit/{record_id}/approve")
def api_system_approve(
    record_id: str,
    body: ReviewBody,
    user: Annotated[User, Depends(require_permission("write:approval_review"))],
) -> dict[str, Any]:
    try:
        return approve_and_execute(
            record_id,
            reviewed_by=user.name,
            reviewed_by_user_id=user.id,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/audit/rejection-categories")
def api_rejection_categories(
    _user: Annotated[User, Depends(require_permission("read:audit"))],
) -> dict[str, Any]:
    return {"categories": [{"key": k, "label": v} for k, v in REJECTION_CATEGORIES.items()]}


@router.post("/audit/batch-approve")
def api_system_batch_approve(
    body: BatchReviewBody,
    user: Annotated[User, Depends(require_permission("write:approval_review"))],
) -> dict[str, Any]:
    try:
        return batch_approve(body.ids, reviewed_by=user.name, reviewed_by_user_id=user.id)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/audit/batch-reject")
def api_system_batch_reject(
    body: BatchReviewBody,
    user: Annotated[User, Depends(require_permission("write:approval_review"))],
) -> dict[str, Any]:
    try:
        return batch_reject(body.ids, reviewed_by=user.name, reviewed_by_user_id=user.id,
                            comment=body.comment, rejection_category=body.rejection_category)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/audit/{record_id}/reject")
def api_system_reject(
    record_id: str,
    body: RejectBody,
    user: Annotated[User, Depends(require_permission("write:approval_review"))],
) -> dict[str, Any]:
    try:
        return reject_approval(
            record_id,
            reviewed_by=user.name,
            reviewed_by_user_id=user.id,
            comment=body.comment,
            rejection_category=body.rejection_category,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ── Jobs ──

@router.get("/jobs")
def api_system_jobs(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_jobs(status=status, offset=offset, limit=limit)


@router.get("/jobs/{job_id}")
def api_system_job(
    job_id: str,
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job 不存在")
    return job


# ── Traces / Execution Logs ──

@router.get("/traces")
def api_system_traces(
    _user: Annotated[User, Depends(get_current_user)],
    limit: int = 50,
) -> dict[str, Any]:
    return {"trace_ids": list_traces(limit=limit)}


@router.get("/traces/{trace_id}")
def api_system_trace(
    trace_id: str,
    _user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    spans = get_trace(trace_id)
    if not spans:
        raise HTTPException(404, "Trace 不存在")
    return {"trace_id": trace_id, "spans": spans}


# ── Agent Tools ──

@router.get("/agents/tools")
def api_system_tools(
    _user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    return {"tools": list(TOOL_REGISTRY.keys())}


class ToolInvokeBody(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/agents/tools/invoke")
def api_system_tool_invoke(
    body: ToolInvokeBody,
    _user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        return {"result": invoke_tool(body.tool, **body.params)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ── User Management ──

class SetRolesBody(BaseModel):
    roles: list[str] = Field(default_factory=list)


@router.get("/users")
def api_system_users(
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
    search: str = Query(""),
    role: str = Query(""),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    users, total = list_users_paginated(db, search=search, role_code=role, offset=offset, limit=limit)
    return {"items": [user_to_dict(u) for u in users], "total": total}


@router.put("/users/{user_id}/roles")
def api_system_set_roles(
    user_id: int,
    body: SetRolesBody,
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    user = set_user_roles(db, user_id, body.roles)
    if not user:
        raise HTTPException(404, "用户不存在")
    return {"ok": True, "user": user_to_dict(user)}


@router.post("/feishu/sync-users")
def api_sync_feishu_users(
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    try:
        result = sync_feishu_users_to_db(db)
        db.commit()
        # 审计日志
        from as_platform.audit.log_utils import log_op
        log_op(user_id=_user.id, user_name=_user.name, category="system", action="sync_feishu_users",
               target_type="user", summary=f"飞书用户同步: 新增{result.get('created',0)} 更新{result.get('updated',0)}")
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(500, f"飞书用户同步失败: {e}") from e


# ── Audit Log ──

@router.get("/audit-log")
def api_audit_log(
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
    user_id: int | None = None,
    category: str | None = None,
    action: str | None = None,
    search: str = Query(""),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    from as_platform.db.models import OperationLog
    q = db.query(OperationLog)
    if user_id:
        q = q.filter(OperationLog.user_id == user_id)
    if category:
        q = q.filter(OperationLog.category == category)
    if action:
        q = q.filter(OperationLog.action == action)
    if search:
        like = f"%{search}%"
        from sqlalchemy import or_
        q = q.filter(or_(OperationLog.summary.ilike(like), OperationLog.user_name.ilike(like)))
    total = q.count()
    items = q.order_by(OperationLog.timestamp.desc()).offset(offset).limit(limit).all()
    return {"items": [log.to_dict() for log in items], "total": total}


@router.get("/audit-log/stats")
def api_audit_log_stats(
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    from as_platform.db.models import OperationLog
    from sqlalchemy import func
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(OperationLog).filter(OperationLog.timestamp >= today).count()
    top_users = (
        db.query(OperationLog.user_name, func.count().label("cnt"))
        .filter(OperationLog.timestamp >= today)
        .group_by(OperationLog.user_name).order_by(func.count().desc()).limit(5).all()
    )
    by_category = (
        db.query(OperationLog.category, func.count().label("cnt"))
        .filter(OperationLog.timestamp >= today)
        .group_by(OperationLog.category).all()
    )
    return {
        "today_count": today_count,
        "top_users": [{"name": name, "count": cnt} for name, cnt in top_users],
        "by_category": [{"category": cat, "count": cnt} for cat, cnt in by_category],
    }

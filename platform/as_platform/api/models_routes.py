"""模型管理 API 路由 — 模块化前缀 /api/v1/models

本路由将 training/* 功能以模块化路径重新暴露，同时保留旧路径兼容。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from as_platform.auth.deps import can_submit_action, get_current_user, require_permission
from as_platform.db.models import User
from as_platform.data.versions import create_snapshot, diff_versions, get_version, list_versions
from as_platform.training.service import (
    TRAINING_ACTIONS,
    create_training_submission,
    get_model_registry,
    get_training_record,
    list_training_records,
)

router = APIRouter(prefix="/api/v1/models", tags=["models"])


class CreateTrainingBody(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


@router.get("/actions")
def api_models_actions(_user: Annotated[User, Depends(require_permission("read:jobs"))]) -> dict[str, Any]:
    """可用的训练/评估/晋级操作列表"""
    from as_platform.audit.queue import ACTION_LABELS

    return {
        "actions": [
            {"id": action, "label": ACTION_LABELS.get(action, action)}
            for action in sorted(TRAINING_ACTIONS)
        ]
    }


@router.get("/registry")
def api_models_registry(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    project: str = Query("dms"),
    task: str | None = None,
) -> dict[str, Any]:
    """模型注册表"""
    return get_model_registry(project=project, task=task)


@router.get("/records")
def api_models_records(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    project: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    task: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """训练/评估记录列表"""
    return list_training_records(
        project=project, kind=kind, status=status, task=task, offset=offset, limit=limit
    )


@router.get("/records/{record_id}")
def api_models_record(
    record_id: str,
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
) -> dict[str, Any]:
    """单条训练记录详情"""
    rec = get_training_record(record_id)
    if not rec:
        raise HTTPException(404, "训练记录不存在")
    return rec


@router.post("/records")
def api_models_create_record(
    body: CreateTrainingBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """提交训练/评估/晋级申请"""
    if not can_submit_action(user, body.action):
        raise HTTPException(403, f"无权提交: {body.action}")
    try:
        return create_training_submission(
            body.action,
            body.params,
            submitted_by=user.name,
            submitted_by_user_id=user.id,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ── 数据集版本管理 ──

class CreateSnapshotBody(BaseModel):
    project: str = "dms"
    description: str = ""


@router.get("/datasets")
def api_list_dataset_versions(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    project: str = Query("dms"),
) -> dict[str, Any]:
    return {"items": list_versions(project)}


@router.post("/datasets/snapshot")
def api_create_snapshot(
    body: CreateSnapshotBody,
    user: Annotated[User, Depends(require_permission("write:approval_submit"))],
) -> dict[str, Any]:
    try:
        result = create_snapshot(body.project, body.description, author=user.name)
        from as_platform.audit.log_utils import log_op
        log_op(user_id=user.id, user_name=user.name, category="data", action="create_snapshot",
               target_type="snapshot", target_id=result.get("version_id"), summary=f"创建快照: {result.get('version_id')} ({body.project})")
        return result
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.get("/datasets/{version_id}")
def api_get_version(
    version_id: str,
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    project: str = Query("dms"),
) -> dict[str, Any]:
    v = get_version(project, version_id)
    if not v:
        raise HTTPException(404, f"版本 {version_id} 不存在")
    return v


@router.get("/datasets/{version_id}/diff")
def api_diff_versions(
    version_id: str,
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    compare: str = Query(...),
    project: str = Query("dms"),
) -> dict[str, Any]:
    result = diff_versions(project, compare, version_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

from __future__ import annotations

import zipfile
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from as_platform.auth.deps import require_any_permission, require_permission
from as_platform.db.models import User
from as_platform.labeling.annotate import (
    campaign_bootstrap,
    campaign_tasks,
    get_annotation,
    resolve_media_file,
    save_annotation,
)
from as_platform.labeling.lock import acquire_lock, release_lock, renew_lock
from as_platform.labeling.progress import (
    assign_tasks_even,
    assign_tasks_explicit,
    assign_tasks_quantized,
    campaign_my_tasks,
    campaign_progress,
    list_my_assignments,
    release_task_assignment,
    reassign_task,
    user_is_coordinator,
)
from as_platform.labeling.service import (
    assign_campaign,
    get_campaign,
    list_campaign_export_jobs,
    list_labeling_assignees,
    list_labeling_batches,
    open_campaign,
    submit_campaign,
    trigger_labeling_export,
    get_batch_export_stats,
    trigger_cuboid_fit,
)
from as_platform.labeling.vendor_import import import_vendor_zip, list_registry_profiles

router = APIRouter(tags=["labeling"])


class OpenCampaignBody(BaseModel):
    project: str = Field(..., pattern="^(dms|lane|adas)$")
    task: str
    batch: str
    mode: str | None = None
    pack: str | None = None
    location: str = "inbox"
    annotation_types: list[str] | None = None


class AssignCampaignBody(BaseModel):
    user_id: int | None = None


class AnnotationBody(BaseModel):
    result: list[dict[str, Any]] | dict[str, Any] | None = None
    annotations: list[dict[str, Any]] | None = None


class AssignTasksExplicitItem(BaseModel):
    user_id: int
    task_ids: list[str] = Field(default_factory=list)


class AssignTasksQuantizedItem(BaseModel):
    user_id: int
    count: int = 0


class AssignTasksBody(BaseModel):
    mode: str = "even"
    user_ids: list[int] | None = None
    items: list[AssignTasksExplicitItem] | None = None
    quantized_items: list[AssignTasksQuantizedItem] | None = None


class ReassignTaskBody(BaseModel):
    user_id: int


@router.get("/api/v1/labeling/assignees")
def api_labeling_assignees(
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    return list_labeling_assignees()


@router.get("/api/v1/labeling/my-assignments")
def api_my_assignments(
    user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    return list_my_assignments(user.id)


@router.get("/api/v1/labeling/campaigns/{campaign_id}/my-tasks")
def api_campaign_my_tasks(
    campaign_id: str,
    user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return campaign_my_tasks(campaign_id, user.id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.patch("/api/v1/labeling/campaigns/{campaign_id}/assign")
def api_assign_campaign(
    campaign_id: str,
    body: AssignCampaignBody,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return assign_campaign(campaign_id, body.user_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/v1/labeling/batches")
def api_labeling_batches(
    _user: Annotated[User, Depends(require_permission("read:pending"))],
    stage: str | None = Query(None),
    stages: str | None = Query(None, description="逗号分隔多阶段，一次扫描返回"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    refresh: bool = Query(False, description="true 时先重建索引再返回"),
    q: str | None = Query(None, description="搜索批次名/任务/项目"),
) -> dict[str, Any]:
    stage_list = [s.strip() for s in stages.split(",")] if stages else None
    return list_labeling_batches(
        stage=stage, stages=stage_list, offset=offset, limit=limit, refresh=refresh, q=q,
    )


@router.post("/api/v1/labeling/batches/rebuild-index")
def api_rebuild_batch_index(
    _user: Annotated[User, Depends(require_permission("write:labeling_assign"))],
) -> dict[str, Any]:
    from as_platform.labeling.batch_index import rebuild_batch_index

    return rebuild_batch_index()


@router.post("/api/v1/labeling/batches/{campaign_id}/archive")
def api_archive_batch(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("write:labeling_assign"))],
) -> dict[str, Any]:
    from as_platform.labeling.batch_index import archive_batch

    try:
        return archive_batch(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "batch not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/v1/labeling/campaigns/open")
def api_open_campaign(
    body: OpenCampaignBody,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    return open_campaign(
        project=body.project,
        task=body.task,
        batch=body.batch,
        mode=body.mode,
        pack=body.pack,
        location=body.location,
    )


@router.get("/api/v1/labeling/campaigns/{campaign_id}")
def api_get_campaign(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    row = get_campaign(campaign_id)
    if not row:
        raise HTTPException(404, "campaign not found")
    return row


@router.get("/api/v1/labeling/campaigns/{campaign_id}/bootstrap")
def api_campaign_bootstrap(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return campaign_bootstrap(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/v1/labeling/campaigns/{campaign_id}/progress")
def api_campaign_progress(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return campaign_progress(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.post("/api/v1/labeling/campaigns/{campaign_id}/assign-tasks")
def api_assign_tasks(
    campaign_id: str,
    body: AssignTasksBody,
    user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "read:pending"))],
) -> dict[str, Any]:
    if not user_is_coordinator(user):
        raise HTTPException(403, "仅协调员可分配任务")
    try:
        if body.mode == "explicit":
            items = [{"user_id": i.user_id, "task_ids": i.task_ids} for i in (body.items or [])]
            return assign_tasks_explicit(campaign_id, items, assigned_by_user_id=user.id)
        if body.mode == "quantized":
            items = [{"user_id": i.user_id, "count": i.count} for i in (body.quantized_items or [])]
            return assign_tasks_quantized(campaign_id, items, assigned_by_user_id=user.id)
        if not body.user_ids:
            raise ValueError("even 模式需要 user_ids")
        return assign_tasks_even(campaign_id, body.user_ids, assigned_by_user_id=user.id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/api/v1/labeling/campaigns/{campaign_id}/assignments/{task_id}")
def api_reassign_task(
    campaign_id: str,
    task_id: str,
    body: ReassignTaskBody,
    user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "read:pending"))],
) -> dict[str, Any]:
    if not user_is_coordinator(user):
        raise HTTPException(403, "仅协调员可改派任务")
    try:
        return reassign_task(campaign_id, task_id, body.user_id)
    except FileNotFoundError:
        raise HTTPException(404, "assignment not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/v1/labeling/campaigns/{campaign_id}/assignments/{task_id}")
def api_release_assignment(
    campaign_id: str,
    task_id: str,
    user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "read:pending"))],
) -> dict[str, Any]:
    if not user_is_coordinator(user):
        raise HTTPException(403, "仅协调员可释放任务")
    try:
        return release_task_assignment(campaign_id, task_id)
    except FileNotFoundError:
        raise HTTPException(404, "assignment not found") from None


@router.get("/api/v1/labeling/campaigns/{campaign_id}/tasks")
def api_campaign_tasks(
    campaign_id: str,
    user: Annotated[User, Depends(require_permission("read:pending"))],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    assignee: str | None = Query(None),
) -> dict[str, Any]:
    try:
        eff = assignee
        if eff is None and not user_is_coordinator(user):
            eff = "me"
        return campaign_tasks(campaign_id, offset=offset, limit=limit, user=user, assignee=eff)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/v1/labeling/media/{campaign_id}/{file_path:path}")
def api_labeling_media(
    campaign_id: str,
    file_path: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
):
    try:
        target = resolve_media_file(campaign_id, file_path)
    except FileNotFoundError:
        raise HTTPException(404, "not found") from None
    except PermissionError:
        raise HTTPException(403, "forbidden") from None
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return FileResponse(target)


@router.get("/api/v1/labeling/campaigns/{campaign_id}/annotations/{task_id}")
def api_get_annotation(
    campaign_id: str,
    task_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return get_annotation(campaign_id, task_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.put("/api/v1/labeling/campaigns/{campaign_id}/annotations/{task_id}")
def api_put_annotation(
    campaign_id: str,
    task_id: str,
    body: AnnotationBody,
    user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return save_annotation(campaign_id, task_id, body.model_dump(exclude_none=True), user=user)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/v1/labeling/campaigns/{campaign_id}/export")
def api_labeling_export(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return trigger_labeling_export(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.get("/api/v1/labeling/campaigns/{campaign_id}/export-stats")
def api_batch_export_stats(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return get_batch_export_stats(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.post("/api/v1/labeling/campaigns/{campaign_id}/cuboid-fit")
def api_cuboid_fit(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return trigger_cuboid_fit(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/v1/labeling/campaigns/{campaign_id}/export-jobs")
def api_campaign_export_jobs(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
    limit: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    if not get_campaign(campaign_id):
        raise HTTPException(404, "campaign not found")
    return list_campaign_export_jobs(campaign_id, limit=limit)


@router.post("/api/v1/labeling/campaigns/{campaign_id}/submit")
def api_campaign_submit(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    try:
        return submit_campaign(campaign_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.get("/api/v1/labeling/registry-profiles")
def api_labeling_registry_profiles(
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    return list_registry_profiles()


@router.post("/api/v1/labeling/campaigns/{campaign_id}/import-vendor")
async def api_import_vendor(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("write:labeling_vendor"))],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    raw = await file.read()
    try:
        return import_vendor_zip(campaign_id, raw)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except (zipfile.BadZipFile, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/v1/labeling/campaigns/{campaign_id}/tasks/{task_id}/lock")
def api_labeling_lock_acquire(
    campaign_id: str,
    task_id: str,
    user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    if not get_campaign(campaign_id):
        raise HTTPException(404, "campaign not found")
    result = acquire_lock(campaign_id, task_id, user_id=user.id, user_name=user.name)
    if not result.get("ok"):
        raise HTTPException(409, detail=result)
    return result


@router.delete("/api/v1/labeling/campaigns/{campaign_id}/tasks/{task_id}/lock")
def api_labeling_lock_release(
    campaign_id: str,
    task_id: str,
    user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    result = release_lock(campaign_id, task_id, user_id=user.id)
    if not result.get("ok"):
        raise HTTPException(409, detail=result)
    return result


@router.post("/api/v1/labeling/campaigns/{campaign_id}/tasks/{task_id}/lock/renew")
def api_labeling_lock_renew(
    campaign_id: str,
    task_id: str,
    user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    result = renew_lock(campaign_id, task_id, user_id=user.id)
    if not result.get("ok"):
        raise HTTPException(409, detail=result)
    return result


# ── CVAT 集成端点 ──


@router.get("/api/v1/labeling/cvat/status/{campaign_id}")
def api_cvat_status(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    from as_platform.labeling.service import get_cvat_status
    try:
        return get_cvat_status(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None


@router.post("/api/v1/labeling/cvat/sync/{campaign_id}")
def api_cvat_sync(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    from as_platform.labeling.service import sync_cvat_annotations
    try:
        return sync_cvat_annotations(campaign_id)
    except FileNotFoundError:
        raise HTTPException(404, "campaign not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"CVAT 同步失败: {e}") from e


# ── 标注质检 (Quality Review) ──

class ReviewScoreBody(BaseModel):
    image_path: str
    score: str  # good / fine / bad
    comment: str | None = None


class ReviewBatchBody(BaseModel):
    scores: list[ReviewScoreBody]


@router.get("/api/v1/labeling/campaigns/{campaign_id}/review-queue")
def api_review_queue(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("write:approval_review"))],
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    from as_platform.audit.review import get_review_queue
    return get_review_queue(campaign_id, offset=offset, limit=limit)


@router.get("/api/v1/labeling/campaigns/{campaign_id}/review-image")
def api_review_image(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("write:approval_review"))],
    path: str = Query(...),
) -> FileResponse:
    from as_platform.audit.review import get_review_image
    import tempfile
    try:
        data = get_review_image(campaign_id, path)
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(data)
        tmp.close()
        return FileResponse(tmp.name, media_type="image/jpeg")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/api/v1/labeling/campaigns/{campaign_id}/review-submit")
def api_review_submit(
    campaign_id: str,
    body: ReviewBatchBody,
    user: Annotated[User, Depends(require_permission("write:approval_review"))],
) -> dict[str, Any]:
    from as_platform.audit.review import submit_review_scores
    items = [s.model_dump() for s in body.scores]
    return submit_review_scores(campaign_id, items, reviewer_user_id=user.id, reviewer_name=user.name)


@router.get("/api/v1/labeling/campaigns/{campaign_id}/review-progress")
def api_review_progress(
    campaign_id: str,
    _user: Annotated[User, Depends(require_permission("read:pending"))],
) -> dict[str, Any]:
    from as_platform.audit.review import review_progress
    return review_progress(campaign_id)


@router.get("/api/v1/labeling/review-progress")
def api_review_progress_batch(
    _user: Annotated[User, Depends(require_permission("read:pending"))],
    campaign_ids: str = Query(..., description="逗号分隔 campaign id，最多 50 个"),
) -> dict[str, Any]:
    from as_platform.audit.review import review_progress_batch
    ids = [x.strip() for x in campaign_ids.split(",") if x.strip()]
    return review_progress_batch(ids)

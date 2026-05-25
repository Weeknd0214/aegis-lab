#!/usr/bin/env python3
"""统一 API + React Web。cd HSAP && PYTHONPATH=platform python -m as_platform.api.server"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
import threading

try:
    from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, Response
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
except ImportError as e:
    raise SystemExit("需要安装: pip install fastapi uvicorn pydantic sqlalchemy python-jose httpx") from e

from as_platform.agents.graphs.ingest_flow import run_ingest_flow
from as_platform.agents.graphs.labeling_flow import run_labeling_flow
from as_platform.agents.graphs.train_promote_flow import run_train_promote_flow
from as_platform.agents.tools import TOOL_REGISTRY, invoke_tool
from as_platform.agents.trace import get_trace, list_traces
from as_platform.api.auth_routes import router as auth_router
from as_platform.audit.queue import (
    ACTION_LABELS,
    ACTIONS_REQUIRING_APPROVAL,
    approve_and_execute,
    get_approval,
    list_approvals,
    reject_approval,
    submit_approval,
)
from as_platform.audit.preview import find_image_ref, list_scope_images, render_overlay, resolve_approval_scope
from as_platform.auth.deps import can_submit_action, get_current_user, require_any_permission, require_permission
from as_platform.config import IS_POSTGRES, PLATFORM_DIR, PLATFORM_WEB, WORKSPACE
from as_platform.data.core import get_catalog, get_pending_report, register_batch, warmup_catalog_cache
from as_platform.data.ingest import UnknownFormatError, inspect_uploaded_dataset
from as_platform.data.lake import (
    create_uploaded_candidate,
    get_candidate,
    link_candidate_analysis_job,
    list_candidates as list_data_candidates,
    write_candidate_upload,
)
from as_platform.data.organize import organize_batch
from as_platform.db.engine import check_connection
from as_platform.db.init_db import init_database
from as_platform.db.models import User
from as_platform.jobs.queue import enqueue_job, get_job, list_jobs
from as_platform.redis.bus import ping_redis
from as_platform.training.service import (
    TRAINING_ACTIONS,
    create_training_submission,
    get_model_registry,
    get_training_record,
    list_training_records,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    threading.Thread(target=warmup_catalog_cache, daemon=True, name="catalog-warmup").start()
    yield


app = FastAPI(title="华胥智能主动安全平台", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
_UI_DIR: Path | None = None


class SubmitApprovalBody(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    submitted_by: str | None = None
    note: str | None = None


class ReviewBody(BaseModel):
    reviewed_by: str | None = None
    comment: str | None = None


class RegisterBatchBody(BaseModel):
    project: str
    task: str | None = None
    batch: str
    pack: str | None = None
    stage: str = "returned"
    engineer: str | None = None
    location: str = "inbox"
    submitted_by: str | None = None
    skip_audit: bool = False


class BuildFromBatchBody(BaseModel):
    project: str = "dms"
    task: str
    batch: str
    pack: str = "dms_v2"
    location: str = "inbox"
    submitted_by: str | None = None
    note: str | None = None


class OrganizeBody(BaseModel):
    batch_path: str
    task: str | None = None


class AgentInvokeBody(BaseModel):
    graph: str = "ingest_flow"
    params: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeBody(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class CreateTrainingBody(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class InspectUploadBody(BaseModel):
    project: str
    task: str | None = None
    source_path: str


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    db_ok = check_connection()
    redis_ok = ping_redis()
    ok = db_ok and redis_ok
    return {
        "status": "ok" if ok else "degraded",
        "workspace": str(WORKSPACE),
        "database": "postgresql" if IS_POSTGRES else "sqlite",
        "db_connected": str(db_ok).lower(),
        "redis_connected": str(redis_ok).lower(),
    }


@app.get("/api/v1/pending")
def api_pending(_user: Annotated[User, Depends(require_permission("read:pending"))]) -> dict[str, Any]:
    return get_pending_report()


@app.get("/api/v1/catalog")
def api_catalog(
    _user: Annotated[User, Depends(require_permission("read:catalog"))],
    refresh: bool = Query(False),
) -> dict[str, Any]:
    return get_catalog(refresh=refresh)


@app.get("/api/v1/catalog/dms/{task}")
def api_catalog_dms(
    task: str,
    _user: Annotated[User, Depends(require_permission("read:catalog"))],
    refresh: bool = Query(False),
) -> dict[str, Any]:
    full = get_catalog(refresh=refresh)
    if task not in (full.get("dms") or {}):
        raise HTTPException(404, f"未知 DMS 任务: {task}")
    return {"task": task, **full["dms"][task]}


@app.get("/api/v1/catalog/lane/{pack}")
def api_catalog_lane(
    pack: str,
    _user: Annotated[User, Depends(require_permission("read:catalog"))],
    refresh: bool = Query(False),
) -> dict[str, Any]:
    full = get_catalog(refresh=refresh)
    if pack not in (full.get("lane") or {}):
        raise HTTPException(404, f"未知 Lane 包: {pack}")
    return {"pack": pack, **full["lane"][pack]}


@app.get("/api/v1/actions")
def api_actions(_user: Annotated[User, Depends(require_permission("read:audit"))]) -> dict[str, Any]:
    return {"actions": [{"id": k, "label": ACTION_LABELS.get(k, k)} for k in sorted(ACTIONS_REQUIRING_APPROVAL)]}


@app.get("/api/v1/jobs")
def api_jobs(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    status: str | None = None,
    limit: int = Query(100, le=500),
) -> dict[str, Any]:
    return {"items": list_jobs(status=status, limit=limit)}


@app.get("/api/v1/jobs/{job_id}")
def api_job(job_id: str, _user: Annotated[User, Depends(require_permission("read:jobs"))]) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job 不存在")
    return job


@app.get("/api/v1/training/actions")
def api_training_actions(_user: Annotated[User, Depends(require_permission("read:jobs"))]) -> dict[str, Any]:
    return {
        "actions": [
            {"id": action, "label": ACTION_LABELS.get(action, action)}
            for action in sorted(TRAINING_ACTIONS)
        ]
    }


@app.get("/api/v1/training/records")
def api_training_records(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    project: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    task: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    return list_training_records(project=project, kind=kind, status=status, task=task, limit=limit)


@app.get("/api/v1/training/records/{job_id}")
def api_training_record(
    job_id: str,
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
) -> dict[str, Any]:
    rec = get_training_record(job_id)
    if not rec:
        raise HTTPException(404, "训练记录不存在")
    return rec


@app.get("/api/v1/training/models")
def api_training_models(
    _user: Annotated[User, Depends(require_permission("read:jobs"))],
    project: str = Query("dms"),
    task: str | None = None,
) -> dict[str, Any]:
    return get_model_registry(project=project, task=task)


@app.post("/api/v1/training/records")
def api_create_training(
    body: CreateTrainingBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
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


@app.get("/api/v1/traces")
def api_traces(_user: Annotated[User, Depends(get_current_user)], limit: int = 50) -> dict[str, Any]:
    return {"trace_ids": list_traces(limit=limit)}


@app.get("/api/v1/traces/{trace_id}")
def api_trace(trace_id: str, _user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    spans = get_trace(trace_id)
    if not spans:
        raise HTTPException(404, "Trace 不存在")
    return {"trace_id": trace_id, "spans": spans}


@app.get("/api/v1/agents/tools")
def api_tools(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    return {"tools": list(TOOL_REGISTRY.keys())}


@app.post("/api/v1/agents/tools/invoke")
def api_tool_invoke(body: ToolInvokeBody, _user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    try:
        return {"result": invoke_tool(body.tool, **body.params)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/agents/invoke")
def api_agent_invoke(body: AgentInvokeBody, _user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    graphs = {
        "ingest_flow": run_ingest_flow,
        "labeling_flow": run_labeling_flow,
        "train_promote_flow": run_train_promote_flow,
    }
    fn = graphs.get(body.graph)
    if not fn:
        raise HTTPException(400, f"未知 graph: {body.graph}")
    return fn(**body.params)


@app.get("/api/v1/approvals")
def api_list_approvals(
    _user: Annotated[User, Depends(require_permission("read:audit"))],
    status: str | None = None,
    limit: int = Query(100, le=500),
) -> dict[str, Any]:
    return {"items": list_approvals(status=status, limit=limit)}


@app.get("/api/v1/approvals/{record_id}")
def api_get_approval(record_id: str, _user: Annotated[User, Depends(require_permission("read:audit"))]) -> dict[str, Any]:
    rec = get_approval(record_id)
    if not rec:
        raise HTTPException(404, "审核单不存在")
    return rec


@app.get("/api/v1/approvals/{record_id}/preview")
def api_approval_preview(
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
    batch_summaries = []
    for b in scope.get("batches") or []:
        batch_dir = Path(b["path"])
        batch_summaries.append(
            {
                "batch": b.get("batch"),
                "location": b.get("location"),
                "path": str(batch_dir) if batch_dir.is_dir() else None,
                "exists": batch_dir.is_dir(),
            }
        )
    return {
        "approval": rec,
        "scope_label": scope.get("scope_label"),
        "task": scope.get("task"),
        "pack": scope.get("pack"),
        "class_names": scope.get("class_names"),
        "batches": batch_summaries,
    }


@app.get("/api/v1/approvals/{record_id}/images")
def api_approval_images(
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


@app.get("/api/v1/approvals/{record_id}/images/{image_id}")
def api_approval_image(
    record_id: str,
    image_id: str,
    _user: Annotated[User, Depends(require_permission("read:audit"))],
    thumb: bool = Query(True),
) -> Response:
    rec = get_approval(record_id)
    if not rec:
        raise HTTPException(404, "审核单不存在")
    try:
        scope = resolve_approval_scope(rec["action"], rec.get("params") or {})
        ref = find_image_ref(scope, image_id)
        if not ref or not ref.image_path.is_file():
            raise HTTPException(404, "图像不存在")
        class_names = scope.get("class_names") or {}
        max_size = 480 if thumb else 1920
        data = render_overlay(ref.image_path, ref.label_path, class_names, max_size=max_size)
        return Response(content=data, media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/approvals/submit")
def api_submit(body: SubmitApprovalBody, user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
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


@app.post("/api/v1/approvals/submit-build-batch")
def api_submit_build_batch(body: BuildFromBatchBody, user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    if not can_submit_action(user, "build_dms"):
        raise HTTPException(403, "无权提交 build")
    params: dict[str, Any] = {"task": body.task, "pack": body.pack}
    if body.location == "inbox":
        params["batch"] = body.batch
    else:
        params["all_sources"] = True
    return submit_approval(
        "build_dms", params,
        submitted_by=user.name,
        submitted_by_user_id=user.id,
        note=body.note or f"入库 {body.batch}",
    )


@app.post("/api/v1/approvals/{record_id}/approve")
def api_approve(record_id: str, body: ReviewBody, user: Annotated[User, Depends(require_permission("write:approval_review"))]) -> dict[str, Any]:
    try:
        return approve_and_execute(
            record_id,
            reviewed_by=user.name,
            reviewed_by_user_id=user.id,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/approvals/{record_id}/reject")
def api_reject(record_id: str, body: ReviewBody, user: Annotated[User, Depends(require_permission("write:approval_review"))]) -> dict[str, Any]:
    try:
        return reject_approval(
            record_id,
            reviewed_by=user.name,
            reviewed_by_user_id=user.id,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/register-batch")
def api_register_batch(body: RegisterBatchBody, user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    if body.skip_audit:
        if not can_submit_action(user, "register_batch"):
            raise HTTPException(403, "无权登记批次")
        try:
            return register_batch(None, body.project, body.task, body.batch, pack=body.pack, stage=body.stage, engineer=body.engineer, location=body.location)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e)) from e
    if not can_submit_action(user, "register_batch"):
        raise HTTPException(403, "无权提交登记审核")
    return submit_approval(
        "register_batch",
        body.model_dump(exclude={"submitted_by", "skip_audit"}),
        submitted_by=user.name,
        submitted_by_user_id=user.id,
        note="登记 batch.meta",
    )


@app.post("/api/v1/data/organize")
def api_organize(body: OrganizeBody, _user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    try:
        return organize_batch(Path(body.batch_path), task=body.task)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/v1/data/inspect-upload")
def api_inspect_upload(body: InspectUploadBody, _user: Annotated[User, Depends(require_permission("read:catalog"))]) -> dict[str, Any]:
    try:
        result = inspect_uploaded_dataset(body.project, body.task, body.source_path)
        return {"ok": True, "normalized": result.to_dict()}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except UnknownFormatError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/data/upload/file")
async def api_upload_file(
    project: Annotated[str, Form()],
    user: Annotated[User, Depends(require_any_permission("write:approval_submit", "write:approval_submit:register"))],
    task: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(400, "上传文件名不能为空")
    try:
        candidate = create_uploaded_candidate(
            project=project,
            task=task,
            original_name=file.filename,
            upload_size_bytes=0,
            submitted_by_name=user.name if user else None,
            submitted_by_user_id=user.id if user else None,
        )
        write_candidate_upload(candidate["id"], file.file)
        job = enqueue_job("analyze_uploaded_dataset", {"candidate_id": candidate["id"]}, async_run=True)
        link_candidate_analysis_job(candidate["id"], job["id"])
        updated = get_candidate(candidate["id"]) or candidate
        return {"ok": True, "candidate": updated, "job": job}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        await file.close()


@app.get("/api/v1/data/candidates")
def api_data_candidates(
    _user: Annotated[User, Depends(require_permission("read:catalog"))],
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    return {"items": list_data_candidates(limit=limit)}


@app.get("/api/v1/data/candidates/{candidate_id}")
def api_data_candidate(candidate_id: str, _user: Annotated[User, Depends(require_permission("read:catalog"))]) -> dict[str, Any]:
    item = get_candidate(candidate_id)
    if not item:
        raise HTTPException(404, "candidate 不存在")
    return item


def _mount_ui() -> None:
    global _UI_DIR
    for ui in (PLATFORM_WEB, PLATFORM_DIR / "web" / "dist"):
        if (ui / "index.html").is_file():
            _UI_DIR = ui
            app.mount("/assets", StaticFiles(directory=str(ui / "assets")), name="ui-assets")
            return


_mount_ui()


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not Found")
    if not _UI_DIR:
        raise HTTPException(404, "UI not built")

    safe = Path(full_path).as_posix().lstrip("/")
    target = (_UI_DIR / safe).resolve()
    ui_root = _UI_DIR.resolve()
    if safe and target.is_file() and target.is_relative_to(ui_root):
        return FileResponse(target)
    return FileResponse(_UI_DIR / "index.html")


@app.head("/{full_path:path}", include_in_schema=False)
def spa_fallback_head(full_path: str):
    return spa_fallback(full_path)


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="华胥智能主动安全平台")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

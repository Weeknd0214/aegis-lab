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
from as_platform.api.fleet_routes import router as fleet_router
from as_platform.api.delivery_routes import router as delivery_router
from as_platform.api.feishu_routes import router as feishu_router
from as_platform.api.labeling_routes import router as labeling_router
from as_platform.api.models_routes import router as models_router
from as_platform.api.system_routes import router as system_router
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
from as_platform.config import (
    FEISHU_BITABLE_SYNC_ENABLED,
    FEISHU_BITABLE_SYNC_INTERVAL_SEC,
    FLEET_MOCK_SIMULATE,
    FLEET_SIM_INTERVAL_SEC,
    IS_POSTGRES,
    PLATFORM_DIR,
    PLATFORM_WEB,
    WORKSPACE,
)
from as_platform.data.core import get_catalog, get_pending_report, register_batch, warmup_catalog_cache
from as_platform.data.ingest import UnknownFormatError, inspect_uploaded_dataset
from as_platform.data.lake import (
    create_uploaded_candidate,
    get_candidate,
    link_candidate_analysis_job,
    list_candidates as list_data_candidates,
    promote_candidate_to_inbox,
    write_candidate_upload,
)
from as_platform.data.organize import organize_batch
from as_platform.db.engine import check_connection, session_scope
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


def _feishu_bitable_sync_loop() -> None:
    import time

    from as_platform.jobs.feishu_bitable_sync import run_sync_cycle

    while True:
        time.sleep(FEISHU_BITABLE_SYNC_INTERVAL_SEC)
        try:
            run_sync_cycle()
        except Exception:
            pass


def _fleet_sim_loop() -> None:
    import time
    from as_platform.fleet import service as fleet_svc
    while True:
        time.sleep(max(3, FLEET_SIM_INTERVAL_SEC))
        try:
            with session_scope() as db:
                fleet_svc.simulate_tick(db)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    threading.Thread(target=warmup_catalog_cache, daemon=True, name="catalog-warmup").start()
    if FLEET_MOCK_SIMULATE:
        threading.Thread(target=_fleet_sim_loop, daemon=True, name="fleet-sim",).start()
    if FEISHU_BITABLE_SYNC_ENABLED:
        threading.Thread(target=_feishu_bitable_sync_loop, daemon=True, name="feishu-bitable-sync").start()
    yield


app = FastAPI(title="华胥智能主动安全平台", version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(fleet_router)
app.include_router(labeling_router)
app.include_router(feishu_router)
app.include_router(delivery_router)
app.include_router(models_router)   # 模型管理: /api/v1/models/*
app.include_router(system_router)   # 系统管理: /api/v1/system/*
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


@app.get("/api/v1/pending/gates")
def api_pending_gates(_user: Annotated[User, Depends(require_permission("read:pending"))]) -> dict[str, Any]:
    """ML 自动化 P0：build 门禁与 manifest 对齐说明。"""
    return {
        "build_validate": (
            "python as.py build dms <task> <pack> 入库后默认执行 scripts/validate_dms_tasks.py；"
            "仅调试可用 --skip-validate"
        ),
        "manifest_smoke": "bash HSAP/scripts/smoke_manifest_alignment.sh",
        "pending_cli": "python as.py pending",
    }


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
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_jobs(status=status, offset=offset, limit=limit)


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
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_training_records(
        project=project, kind=kind, status=status, task=task, offset=offset, limit=limit
    )


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
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_approvals(status=status, offset=offset, limit=limit)


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
    params = rec.get("params") or {}
    title = str(rec.get("action_label") or rec.get("action") or record_id)
    summary = ""
    if rec.get("action") == "delivery_ingest":
        title = f"数据送标入湖 · {params.get('batch_name') or '—'}"
        parts = [
            f"项目 {params.get('project') or 'dms'}",
            f"任务 {params.get('task') or '—'}",
            f"路径 {params.get('data_path') or '—'}",
        ]
        if params.get("estimated_count"):
            parts.append(f"约 {params['estimated_count']} 张")
        summary = " · ".join(parts)
    return {
        "approval": rec,
        "title": title,
        "summary": summary,
        "scope_label": scope.get("scope_label"),
        "task": scope.get("task"),
        "pack": scope.get("pack"),
        "class_names": scope.get("class_names"),
        "batches": batch_summaries,
        "delivery": params if rec.get("action") == "delivery_ingest" else None,
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
    return submit_approval(
        action, params,
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
    result = None
    if body.skip_audit:
        if not can_submit_action(user, "register_batch"):
            raise HTTPException(403, "无权登记批次")
        try:
            result = register_batch(None, body.project, body.task, body.batch, pack=body.pack, stage=body.stage, engineer=body.engineer, location=body.location)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e)) from e
    else:
        if not can_submit_action(user, "register_batch"):
            raise HTTPException(403, "无权提交登记审核")
        result = submit_approval(
            "register_batch",
            body.model_dump(exclude={"submitted_by", "skip_audit"}),
            submitted_by=user.name,
            submitted_by_user_id=user.id,
            note="登记 batch.meta",
        )
    # 审计日志
    from as_platform.audit.log_utils import log_op
    log_op(user_id=user.id, user_name=user.name, category="data", action="register_batch",
           target_type="batch", target_id=f"{body.project}/{body.task}/{body.batch}", summary=f"登记批次: {body.project}/{body.task}/{body.batch} → {body.stage}")
    return result


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
    mode: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(400, "上传文件名不能为空")
    try:
        candidate = create_uploaded_candidate(
            project=project,
            task=task,
            mode=mode,
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
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_data_candidates(offset=offset, limit=limit)


@app.get("/api/v1/data/candidates/{candidate_id}")
def api_data_candidate(candidate_id: str, _user: Annotated[User, Depends(require_permission("read:catalog"))]) -> dict[str, Any]:
    item = get_candidate(candidate_id)
    if not item:
        raise HTTPException(404, "candidate 不存在")
    return item


class PromoteInboxBody(BaseModel):
    batch: str | None = None
    mode: str | None = None


@app.post("/api/v1/data/candidates/{candidate_id}/promote-inbox")
def api_promote_candidate_inbox(
    candidate_id: str,
    body: PromoteInboxBody,
    _user: Annotated[User, Depends(require_any_permission("write:approval_submit", "write:approval_submit:register"))],
) -> dict[str, Any]:
    try:
        return promote_candidate_to_inbox(candidate_id, batch=body.batch, mode=body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/v1/data/registry-tasks")
def api_registry_tasks(
    _user: Annotated[User, Depends(require_permission("read:catalog"))],
    project: str = Query("dms"),
) -> dict[str, Any]:
    import yaml

    from as_platform.data.core import load_wf, proj_root

    wf = load_wf()
    if project != "dms":
        return {"project": project, "tasks": {}}
    root = proj_root(wf, "dms")
    reg_path = root / wf["projects"]["dms"]["registry"]
    if not reg_path.is_file():
        return {"project": project, "tasks": {}}
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    import sys

    scripts = WORKSPACE / "datasets" / "dms" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from task_registry import task_defs_for_pending

    return {"project": project, "tasks": task_defs_for_pending(reg)}


@app.get("/api/v1/data/scan-inbox")
def api_scan_inbox(
    _user: Annotated[User, Depends(require_permission("read:catalog"))],
    project: str = Query("dms"),
) -> dict[str, Any]:
    """扫描 inbox 目录，返回未登记的新批次。"""
    from as_platform.data.core import load_wf, proj_root
    from as_platform.labeling.batch_index import index_is_empty, rebuild_batch_index

    wf = load_wf()
    root = proj_root(wf, project)
    inbox = root / "inbox"
    if not inbox.is_dir():
        return {"project": project, "items": [], "inbox_path": str(inbox)}

    if index_is_empty():
        rebuild_batch_index(wf)

    from as_platform.db.engine import session_scope
    from as_platform.db.models import BatchIndex

    with session_scope() as db:
        registered = {
            (r.task or "", r.batch)
            for r in db.query(BatchIndex).filter(
                BatchIndex.project == project,
                BatchIndex.archived.is_(False),
            ).all()
        }

    items: list[dict[str, Any]] = []
    for task_dir in sorted(inbox.iterdir()):
        if not task_dir.is_dir():
            continue
        for batch_dir in sorted(task_dir.iterdir()):
            if not batch_dir.is_dir():
                continue
            batch_name = batch_dir.name
            task_name = task_dir.name
            if (task_name, batch_name) in registered:
                continue  # 已登记

            # Count images (含 images/ 子目录)
            from as_platform.data.batch import count_images, count_label_files, dms_has_labels

            img_count = count_images(batch_dir)
            if not img_count and (batch_dir / "images").is_dir():
                img_count = count_images(batch_dir / "images")
            lbl_count = count_label_files(batch_dir / "labels") if (batch_dir / "labels").is_dir() else 0
            has_labels = lbl_count > 0 or dms_has_labels(batch_dir)

            items.append({
                "project": project,
                "task": task_name,
                "batch": batch_name,
                "path": str(batch_dir.relative_to(root)),
                "images": img_count,
                "labels": lbl_count,
                "has_labels": has_labels,
                "stage_hint": "returned" if has_labels and lbl_count > 0 else "raw_pool",
            })

    return {"project": project, "items": items, "inbox_path": str(inbox)}


@app.get("/api/v1/dashboard")
def api_dashboard(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """首页仪表盘聚合数据。"""
    from as_platform.data.core import get_pending_report, get_catalog
    from as_platform.jobs.queue import list_jobs

    # 批次统计
    report = get_pending_report()
    batches = report.get("batches", []) or []
    stage_counts: dict[str, int] = {"raw_pool": 0, "out_for_labeling": 0, "labeling_submitted": 0, "returned": 0, "ingested": 0}
    for b in batches:
        s = b.get("stage", "raw_pool") if isinstance(b, dict) else "raw_pool"
        stage_counts[s] = stage_counts.get(s, 0) + 1

    # 审核统计
    approvals_pending = list_approvals(status="pending", limit=200)
    pending_approvals = approvals_pending.get("total", 0)

    # Job 统计
    jobs_data = list_jobs(limit=5)
    jobs = jobs_data.get("items", []) or []
    running_jobs = len([j for j in jobs if isinstance(j, dict) and j.get("status") == "running"])

    # 模型统计
    try:
        from as_platform.training.service import get_model_registry
        models = get_model_registry(project="dms")
        model_count = len((models.get("models") or []) if isinstance(models, dict) else [])
    except Exception:
        model_count = 0

    # 训练记录
    try:
        from as_platform.training.service import list_training_records
        records = list_training_records(limit=5)
        recent_records = (records.get("items") or [])[:5] if isinstance(records, dict) else []
    except Exception:
        recent_records = []

    # 车队
    try:
        from as_platform.fleet import service as fleet_svc
        from as_platform.db.engine import session_scope
        with session_scope() as db:
            summary = fleet_svc.get_summary(db) if hasattr(fleet_svc, "get_summary") else {}
    except Exception:
        summary = {}

    # 最近活动
    activity: list[dict[str, Any]] = []
    for j in jobs[:5]:
        if isinstance(j, dict):
            activity.append({"type": "job", "id": j.get("id"), "action": j.get("action"), "status": j.get("status"), "time": j.get("created_at")})
    for a in (approvals_pending.get("items") or [])[:3]:
        if isinstance(a, dict):
            activity.append({"type": "approval", "id": a.get("id"), "action": a.get("action_label") or a.get("action"), "status": a.get("status"), "time": a.get("submitted_at")})

    activity.sort(key=lambda x: str(x.get("time") or ""), reverse=True)

    return {
        "stages": stage_counts,
        "total_batches": len(batches),
        "pending_approvals": pending_approvals,
        "running_jobs": running_jobs,
        "model_count": model_count,
        "fleet": summary,
        "activity": activity[:8],
        "recent_training": [{"id": r.get("id"), "action": r.get("action"), "status": r.get("status"), "created_at": r.get("created_at")} for r in recent_records if isinstance(r, dict)],
    }


# ── 世界模型仿真 ──

class SimulateBody(BaseModel):
    scene: str = "urban_highway"
    camera: str = "truck_front"
    weather: str = "clear"
    objects: list[str] = Field(default_factory=lambda: ["Pedestrain", "Car", "Truck", "Bus"])
    density: str = "medium"
    count: int = 100
    fov_variant: bool = False
    note: str = ""


@app.get("/api/v1/simulate/jobs")
def api_simulate_jobs(
    _user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    from as_platform.data.simulate import list_jobs
    return list_jobs(offset=offset, limit=limit)


@app.post("/api/v1/simulate/generate")
def api_simulate_generate(
    body: SimulateBody,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    from as_platform.data.simulate import submit_job
    return submit_job(body.model_dump(), user_name=user.name)


@app.get("/api/v1/simulate/jobs/{job_id}")
def api_simulate_job(
    job_id: str,
    _user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    from as_platform.data.simulate import get_job
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job 不存在")
    return job


@app.get("/api/v1/simulate/jobs/{job_id}/images")
def api_simulate_job_images(
    job_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
) -> dict[str, Any]:
    from as_platform.data.simulate import get_job_images
    return get_job_images(job_id, offset=offset, limit=limit)


@app.post("/api/v1/simulate/jobs/{job_id}/ingest")
def api_simulate_ingest(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    task: str = Query("adas"),
) -> dict[str, Any]:
    from as_platform.data.simulate import ingest_job_to_batch
    return ingest_job_to_batch(job_id, task=task, user_name=user.name)


def _mount_ui() -> None:
    global _UI_DIR
    ui = PLATFORM_WEB
    if (ui / "index.html").is_file():
        _UI_DIR = ui
        assets = ui / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="ui-assets")
        return


_mount_ui()


@app.get("/labeling/campaigns/{campaign_id}/annotate", include_in_schema=False)
def serve_annotate_app_redirect(campaign_id: str):
    """标注编辑器 — 已迁移至 CVAT，302 重定向到新路由"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/labeling/annotate/{campaign_id}", status_code=302)


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

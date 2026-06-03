"""Job 队列（PostgreSQL + 可选 Redis Worker）。"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from as_platform.config import JOB_EXECUTOR
from as_platform.db.engine import session_scope
from as_platform.db.models import Job

_executor_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return f"job-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def enqueue_job(
    action: str,
    params: dict[str, Any],
    *,
    approval_id: str | None = None,
    async_run: bool = True,
) -> dict[str, Any]:
    job_id = _new_id()
    with session_scope() as db:
        job = Job(
            id=job_id,
            status="queued",
            action=action,
            approval_id=approval_id,
            created_at=_now(),
        )
        job.set_params(params)
        db.add(job)

    out = get_job(job_id) or {"id": job_id, "status": "queued", "action": action}

    if not async_run:
        _run_job(job_id)
        return get_job(job_id) or out

    if JOB_EXECUTOR == "worker":
        from as_platform.redis.bus import push_job

        push_job(job_id)
        return out

    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return out


def get_job(job_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        rec = db.get(Job, job_id)
        return rec.to_dict() if rec else None


def list_jobs(
    status: str | None = None,
    *,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    with session_scope() as db:
        q = db.query(Job).order_by(Job.created_at.desc())
        if status:
            q = q.filter(Job.status == status)
        total = q.count()
        rows = q.offset(max(0, offset)).limit(max(1, limit)).all()
        return {
            "items": [j.to_dict() for j in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


def _patch(job_id: str, **fields: Any) -> dict[str, Any] | None:
    with session_scope() as db:
        rec = db.get(Job, job_id)
        if not rec:
            return None
        for k, v in fields.items():
            if k == "result" and isinstance(v, dict):
                rec.set_result(v)
            elif hasattr(rec, k):
                setattr(rec, k, v)
        db.flush()
        return rec.to_dict()


def _compact_result(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        out = dict(payload)
    else:
        out = {"value": payload}
    if "ok" not in out:
        out["ok"] = True
    for k in ("stdout", "stderr"):
        if isinstance(out.get(k), str):
            out[k] = out[k][-8000:]
    return out


def _run_job(job_id: str) -> None:
    with _executor_lock:
        job = get_job(job_id)
        if not job or job.get("status") not in ("queued",):
            return
        _patch(job_id, status="running", started_at=_now())

        from as_platform.agents.trace import trace_span
        from as_platform.jobs.runner import execute_action
        from as_platform.redis.bus import publish

        publish("job.started", {"job_id": job_id, "action": job["action"]})

        try:
            with trace_span("job_start", job_id=job_id, action=job["action"], approval_id=job.get("approval_id")):
                result = execute_action(job["action"], job.get("params") or {})
            persisted = _compact_result(result)
            _patch(
                job_id,
                status="succeeded",
                finished_at=_now(),
                result=persisted,
            )
            publish("job.succeeded", {"job_id": job_id})
            with trace_span("job_end", job_id=job_id, status="succeeded"):
                pass
            _sync_approval(job.get("approval_id"), "executed", persisted)
            if job.get("action") == "labeling_export":
                from as_platform.labeling.batch_stage import on_labeling_export_job_succeeded

                on_labeling_export_job_succeeded(job)
        except Exception as e:
            _patch(job_id, status="failed", finished_at=_now(), result={"ok": False, "error": str(e)})
            publish("job.failed", {"job_id": job_id, "error": str(e)})
            with trace_span("job_end", job_id=job_id, status="failed", error=str(e)):
                pass
            _sync_approval(job.get("approval_id"), "failed", {"error": str(e)})
            if job.get("action") == "delivery_ingest":
                from as_platform.deliveries.service import mark_delivery_ingest_failed

                params = job.get("params") or {}
                mark_delivery_ingest_failed(
                    params.get("delivery_id"),
                    job.get("approval_id"),
                    str(e),
                )


def _sync_approval(approval_id: str | None, status: str, result: dict) -> None:
    if not approval_id:
        return
    from as_platform.audit.queue import _update, _now as audit_now

    _update(
        approval_id,
        status=status,
        executed_at=audit_now(),
        result=result if isinstance(result, dict) and "ok" in result else {"ok": status == "executed", **result},
    )

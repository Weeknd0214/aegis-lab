"""训练记录查询与提交。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from as_platform.audit.queue import ACTION_LABELS, get_approval, submit_approval
from as_platform.config import WORKSPACE
from as_platform.jobs.queue import get_job, list_jobs

TRAINING_ACTIONS = frozenset(
    {
        "train_dms",
        "train_lane",
        "eval_dms",
        "eval_lane",
        "promote_dms",
        "pipeline_dms",
        "visualize_dms",
        "visualize_lane",
    }
)

ACTION_KIND = {
    "train_dms": "train",
    "train_lane": "train",
    "eval_dms": "eval",
    "eval_lane": "eval",
    "promote_dms": "promote",
    "pipeline_dms": "pipeline",
    "visualize_dms": "visualize",
    "visualize_lane": "visualize",
}


def _project_for_action(action: str) -> str:
    if action.endswith("_dms") or action.startswith("promote_dms") or action.startswith("pipeline_dms"):
        return "dms"
    if "lane" in action:
        return "lane"
    return "unknown"


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_sec(job: dict[str, Any]) -> float | None:
    start = _parse_ts(job.get("started_at") or job.get("created_at"))
    end = _parse_ts(job.get("finished_at"))
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def _extract_weight(job: dict[str, Any]) -> str | None:
    params = job.get("params") or {}
    result = job.get("result") or {}
    for key in ("best_weights", "candidate", "model_path", "weights", "run_dir"):
        val = result.get(key) or params.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_metrics(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    metrics: dict[str, Any] = {}
    for key in ("map50", "map50_95", "map", "delta_map50", "precision", "recall", "f1"):
        if key in result and result[key] is not None:
            metrics[key] = result[key]
    if "metrics" in result and isinstance(result["metrics"], dict):
        metrics.update(result["metrics"])
    if "last_eval" in result and isinstance(result["last_eval"], dict):
        metrics.update(result["last_eval"])
    return metrics


def enrich_job(job: dict[str, Any]) -> dict[str, Any]:
    action = job.get("action", "")
    params = job.get("params") or {}
    result = job.get("result") or {}
    approval = get_approval(job["approval_id"]) if job.get("approval_id") else None
    task = params.get("task")
    if action == "train_lane" and not task:
        task = None
    return {
        **job,
        "action_label": ACTION_LABELS.get(action, action),
        "project": _project_for_action(action),
        "kind": ACTION_KIND.get(action, "other"),
        "task": task,
        "track": params.get("track"),
        "weight_path": _extract_weight(job),
        "metrics": _extract_metrics(result),
        "error": result.get("error") if isinstance(result, dict) else None,
        "approval": approval,
        "duration_sec": _duration_sec(job),
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": len(records), "running": 0, "queued": 0, "succeeded": 0, "failed": 0}
    for rec in records:
        status = rec.get("status") or ""
        if status in summary:
            summary[status] += 1
    return summary


def list_training_records(
    *,
    project: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    task: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    jobs = list_jobs(status=status, limit=500)
    records: list[dict[str, Any]] = []
    for job in jobs:
        if job.get("action") not in TRAINING_ACTIONS:
            continue
        rec = enrich_job(job)
        if project and rec["project"] != project:
            continue
        if kind and rec["kind"] != kind:
            continue
        if task and rec.get("task") != task:
            continue
        records.append(rec)
        if len(records) >= limit:
            break
    return {"items": records, "total": len(records), "summary": _summarize(records)}


def get_training_record(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job or job.get("action") not in TRAINING_ACTIONS:
        return None
    return enrich_job(job)


def _read_train_versions() -> dict[str, Any]:
    path = WORKSPACE / "datasets/dms/manifests/train_versions.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _read_eval_log(task: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    path = WORKSPACE / "datasets/dms/manifests/eval_log.jsonl"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if task and row.get("task") != task:
            continue
        entries.append(row)
        if len(entries) >= limit:
            break
    return entries


def get_model_registry(project: str = "dms", task: str | None = None) -> dict[str, Any]:
    if project != "dms":
        return {"project": project, "tasks": {}, "eval_history": []}
    versions = _read_train_versions()
    if task:
        task_data = versions.get(task, {})
        return {
            "project": "dms",
            "task": task,
            "version": task_data,
            "eval_history": _read_eval_log(task=task),
        }
    tasks = {name: data for name, data in versions.items() if isinstance(data, dict)}
    return {"project": "dms", "tasks": tasks, "eval_history": _read_eval_log(limit=20)}


def create_training_submission(
    action: str,
    params: dict[str, Any],
    *,
    submitted_by: str | None = None,
    submitted_by_user_id: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if action not in TRAINING_ACTIONS:
        raise ValueError(f"不支持的动作: {action}")
    return submit_approval(
        action,
        params,
        submitted_by=submitted_by,
        submitted_by_user_id=submitted_by_user_id,
        note=note,
    )

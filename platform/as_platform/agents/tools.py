"""LangChain 风格 Tool 注册（纯 Python + 可选 langchain）。"""
from __future__ import annotations

from typing import Any, Callable

from as_platform.audit.queue import submit_approval
from as_platform.data.core import get_catalog, get_pending_report, load_wf
from as_platform.jobs.queue import get_job, list_jobs

import yaml
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]


def list_pending_batches() -> dict[str, Any]:
    return get_pending_report()


def get_dataset_catalog() -> dict[str, Any]:
    return get_catalog()


def submit_build_for_batch(task: str, batch: str, pack: str = "dms_v2", submitted_by: str | None = None) -> dict:
    return submit_approval(
        "build_dms",
        {"task": task, "pack": pack, "batch": batch},
        submitted_by=submitted_by,
        note=f"agent build {batch}",
    )


def submit_train_job(project: str, task: str, track: str = "platform", submitted_by: str | None = None) -> dict:
    action = "train_dms" if project == "dms" else "train_lane"
    params: dict[str, Any] = {"track": track}
    if project == "dms":
        params["task"] = task
    return submit_approval(action, params, submitted_by=submitted_by, note=f"agent train {project}/{task}")


def get_job_status(job_id: str) -> dict[str, Any] | None:
    return get_job(job_id)


def get_model_versions(task: str) -> dict[str, Any]:
    root = WORKSPACE / "datasets/dms/manifests/train_versions.yaml"
    if not root.is_file():
        return {}
    data = yaml.safe_load(root.read_text(encoding="utf-8"))
    return data.get(task, {})


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "list_pending_batches": list_pending_batches,
    "get_dataset_catalog": get_dataset_catalog,
    "submit_build_for_batch": submit_build_for_batch,
    "submit_train_job": submit_train_job,
    "get_job_status": get_job_status,
    "get_model_versions": get_model_versions,
}


def invoke_tool(name: str, **kwargs: Any) -> Any:
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        raise ValueError(f"未知 tool: {name}")
    return fn(**kwargs)


def as_langchain_tools() -> list[Any]:
    try:
        from langchain_core.tools import tool
    except ImportError:
        return []

    @tool
    def t_list_pending_batches() -> dict:
        """列出待处理批次与送标状态。"""
        return list_pending_batches()

    @tool
    def t_get_dataset_catalog() -> dict:
        """获取 DMS/Lane 数据目录统计。"""
        return get_dataset_catalog()

    return [t_list_pending_batches, t_get_dataset_catalog]

"""train_promote_flow：提交 train 审核（platform 轨）。"""
from __future__ import annotations

from typing import Any

from as_platform.agents.tools import get_model_versions, invoke_tool, submit_train_job
from as_platform.agents.trace import start_trace, trace_span


def run_train_promote_flow(*, task: str = "dam", submitted_by: str = "agent") -> dict[str, Any]:
    trace_id = start_trace("train_promote_flow", task=task)
    with trace_span("get_versions"):
        versions = get_model_versions(task)

    with trace_span("submit_train"):
        apr = submit_train_job("dms", task, track="platform", submitted_by=submitted_by)

    return {"trace_id": trace_id, "versions_before": versions, "approval": apr}

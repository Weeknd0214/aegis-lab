"""ingest_flow：感知 returned 批次 → 提交 build 审核。"""
from __future__ import annotations

from typing import Any

from as_platform.agents.tools import invoke_tool, submit_build_for_batch
from as_platform.agents.trace import start_trace, trace_span


def run_ingest_flow(*, task: str = "dam", submitted_by: str = "agent") -> dict[str, Any]:
    trace_id = start_trace("ingest_flow", task=task)
    with trace_span("list_pending"):
        report = invoke_tool("list_pending_batches")

    submitted = []
    for batch in report.get("batches", []):
        if batch.get("task") != task:
            continue
        if batch.get("stage") != "returned":
            continue
        with trace_span("submit_build", batch=batch.get("batch")):
            apr = submit_build_for_batch(
                task=task,
                batch=batch["batch"],
                pack=batch.get("pack") or "dms_v2",
                submitted_by=submitted_by,
            )
            submitted.append(apr)

    return {"trace_id": trace_id, "submitted": submitted, "count": len(submitted)}

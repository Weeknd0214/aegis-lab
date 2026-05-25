"""labeling_flow：列出 raw_pool / out_for_labeling 批次。"""
from __future__ import annotations

from typing import Any

from as_platform.agents.tools import invoke_tool
from as_platform.agents.trace import start_trace, trace_span


def run_labeling_flow(*, task: str | None = None) -> dict[str, Any]:
    trace_id = start_trace("labeling_flow", task=task)
    with trace_span("list_pending"):
        report = invoke_tool("list_pending_batches")

    batches = [
        b for b in report.get("batches", [])
        if b.get("stage") in ("raw_pool", "out_for_labeling", "returned")
        and (task is None or b.get("task") == task)
    ]
    return {"trace_id": trace_id, "batches": batches, "count": len(batches)}

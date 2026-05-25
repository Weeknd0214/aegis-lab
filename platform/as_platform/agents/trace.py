"""LangSmith 式 trace：manifests/trace_log.jsonl"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from as_platform.config import TRACE_LOG, MANIFESTS

_current_trace: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_trace(name: str, **meta: Any) -> str:
    global _current_trace
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    _current_trace = trace_id
    _append({"type": "trace_start", "trace_id": trace_id, "name": name, "ts": _now(), **meta})
    return trace_id


def _append(entry: dict[str, Any]) -> None:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    if not TRACE_LOG.is_file():
        TRACE_LOG.write_text("", encoding="utf-8")
    with TRACE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@contextmanager
def trace_span(span_type: str, **fields: Any) -> Iterator[None]:
    span_id = f"span-{uuid.uuid4().hex[:8]}"
    _append({"type": span_type, "span_id": span_id, "trace_id": _current_trace, "ts": _now(), **fields})
    try:
        yield
    finally:
        _append({"type": f"{span_type}_end", "span_id": span_id, "trace_id": _current_trace, "ts": _now()})


def get_trace(trace_id: str) -> list[dict[str, Any]]:
    if not TRACE_LOG.is_file():
        return []
    return [json.loads(l) for l in TRACE_LOG.read_text().strip().splitlines() if l.strip() and trace_id in l]


def list_traces(limit: int = 50) -> list[str]:
    if not TRACE_LOG.is_file():
        return []
    ids = []
    for line in TRACE_LOG.read_text().strip().splitlines():
        try:
            o = json.loads(line)
            if o.get("type") == "trace_start" and o.get("trace_id"):
                ids.append(o["trace_id"])
        except json.JSONDecodeError:
            pass
    return list(reversed(ids[-limit:]))

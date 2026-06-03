"""飞书多维表格同步周期任务。"""
from __future__ import annotations

from typing import Any

from as_platform.config import FEISHU_BITABLE_AUTO_INGEST, FEISHU_BITABLE_SYNC_ENABLED
from as_platform.integrations.feishu_bitable import is_bitable_configured
from as_platform.integrations.feishu_bitable_ingest import process_pending_ingest
from as_platform.integrations.feishu_bitable_sync import sync_hsap_to_bitable


def run_sync_cycle() -> dict[str, Any]:
    if not is_bitable_configured():
        return {"ok": False, "message": "飞书多维表格未配置"}

    out: dict[str, Any] = {"ok": True}
    if FEISHU_BITABLE_AUTO_INGEST:
        out["ingest"] = process_pending_ingest()
    out["sync"] = sync_hsap_to_bitable()
    return out


def should_run_background_sync() -> bool:
    return FEISHU_BITABLE_SYNC_ENABLED and is_bitable_configured()

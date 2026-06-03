"""飞书集成 API。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from as_platform.auth.deps import require_any_permission
from as_platform.db.models import User
from as_platform.config import FEISHU_BITABLE_AUTO_INGEST, FEISHU_BITABLE_WEBHOOK_ENABLED
from as_platform.integrations.feishu_bitable import connectivity_check, is_bitable_configured, list_tables
from as_platform.integrations.feishu_bitable_ingest import process_pending_ingest
from as_platform.integrations.feishu_bitable_sync import backfill_hints
from as_platform.integrations.feishu_notify import is_notify_configured
from as_platform.jobs.feishu_bitable_sync import run_sync_cycle

router = APIRouter(prefix="/api/v1/integrations/feishu", tags=["feishu"])


@router.get("/bitable/status")
def api_bitable_status(
    _user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "*"))],
) -> dict[str, Any]:
    return connectivity_check()


@router.get("/bitable/tables")
def api_bitable_tables(
    _user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "*"))],
) -> dict[str, Any]:
    if not is_bitable_configured():
        return {"items": [], "message": "未配置 BITABLE_APP_TOKEN / TABLE_ID"}
    return {"items": list_tables()}


@router.post("/bitable/sync")
def api_bitable_sync(
    _user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "*"))],
) -> dict[str, Any]:
    return run_sync_cycle()


@router.post("/bitable/ingest")
def api_bitable_ingest(
    _user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "*"))],
) -> dict[str, Any]:
    """手动触发「待落盘」入湖（须 FEISHU_BITABLE_AUTO_INGEST=1 或本接口始终可用）。"""
    return process_pending_ingest()


@router.get("/bitable/config")
def api_bitable_config(
    _user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "*"))],
) -> dict[str, Any]:
    return {
        "bitable_configured": is_bitable_configured(),
        "notify_configured": is_notify_configured(),
        "auto_ingest": FEISHU_BITABLE_AUTO_INGEST,
        "webhook_enabled": FEISHU_BITABLE_WEBHOOK_ENABLED,
    }


@router.post("/bitable/webhook")
def api_bitable_webhook_disabled() -> dict[str, Any]:
    """内网默认关闭；有公网穿透后再实现验签入站。"""
    if not FEISHU_BITABLE_WEBHOOK_ENABLED:
        return {"ok": False, "message": "FEISHU_BITABLE_WEBHOOK_ENABLED 未开启"}
    return {"ok": False, "message": "Webhook 处理器尚未实现"}


@router.get("/bitable/backfill-hints")
def api_bitable_backfill_hints(
    _user: Annotated[User, Depends(require_any_permission("write:labeling_assign", "*"))],
) -> dict[str, Any]:
    return backfill_hints()

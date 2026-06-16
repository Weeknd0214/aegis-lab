"""平台批次送标申请 API。"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from as_platform.auth.deps import get_current_user, require_any_permission
from as_platform.db.models import User
from as_platform.deliveries import service as delivery_svc

router = APIRouter(prefix="/api/v1/deliveries", tags=["deliveries"])


class DeliveryBody(BaseModel):
    project: str = "dms"
    task: str | None = None
    mode: str | None = None
    batch_name: str = ""
    source_type: str | None = None
    vehicle_scene: str | None = None
    collection_start: str | None = None
    collection_end: str | None = None
    data_path: str = ""
    estimated_count: int | None = None
    remark: str | None = None
    owner_user_id: int | None = None
    owner_name: str | None = None


class DeliveryPatchBody(BaseModel):
    project: str | None = None
    task: str | None = None
    mode: str | None = None
    batch_name: str | None = None
    source_type: str | None = None
    vehicle_scene: str | None = None
    collection_start: str | None = None
    collection_end: str | None = None
    data_path: str | None = None
    estimated_count: int | None = None
    remark: str | None = None
    owner_user_id: int | None = None
    owner_name: str | None = None


@router.get("/scan")
def api_scan_deliveries(
    _user: Annotated[User, Depends(require_any_permission("read:deliveries", "read:pending", "*"))],
    projects: str | None = Query(None, description="逗号分隔: dms,adas,lane"),
) -> dict[str, Any]:
    from as_platform.deliveries.scan import scan_delivery_sources

    projs = [p.strip() for p in projects.split(",") if p.strip()] if projects else None
    return scan_delivery_sources(projects=projs)


class ScanRegisterBody(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    sync_workbench: bool = True


@router.post("/scan/register")
def api_register_scanned_deliveries(
    body: ScanRegisterBody,
    user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    from as_platform.deliveries.scan import register_scanned_to_ledger

    return register_scanned_to_ledger(body.items, user, sync_workbench=body.sync_workbench)


@router.post("/{delivery_id}/sync-workbench")
def api_sync_delivery_workbench(
    delivery_id: str,
    _user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    from as_platform.deliveries.scan import bridge_delivery_to_workbench

    try:
        return bridge_delivery_to_workbench(delivery_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("")
def api_list_deliveries(
    _user: Annotated[User, Depends(require_any_permission("read:deliveries", "read:pending", "*"))],
    status: str | None = Query(None),
    mine: bool = Query(False),
    mine_editable: bool = Query(False, description="待我处理：仅草稿/驳回"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    mine_id = _user.id if mine or mine_editable else None
    return delivery_svc.list_deliveries(
        status=status,
        mine_user_id=mine_id,
        mine_editable_only=mine_editable,
        offset=offset,
        limit=limit,
    )


@router.get("/{delivery_id}")
def api_get_delivery(
    delivery_id: str,
    _user: Annotated[User, Depends(require_any_permission("read:deliveries", "read:pending", "*"))],
) -> dict[str, Any]:
    row = delivery_svc.get_delivery(delivery_id)
    if not row:
        raise HTTPException(404, "送标申请不存在")
    return row


@router.post("")
def api_create_delivery(
    body: DeliveryBody,
    user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    try:
        return delivery_svc.create_delivery(body.model_dump(), user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/{delivery_id}")
def api_patch_delivery(
    delivery_id: str,
    body: DeliveryPatchBody,
    user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    try:
        return delivery_svc.update_delivery(delivery_id, data, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{delivery_id}/submit")
def api_submit_delivery(
    delivery_id: str,
    user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    try:
        return delivery_svc.submit_delivery_for_review(delivery_id, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/{delivery_id}/retry-ingest")
def api_retry_delivery_ingest(
    delivery_id: str,
    user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    try:
        return delivery_svc.retry_delivery_ingest(delivery_id, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{delivery_id}")
def api_delete_delivery(
    delivery_id: str,
    user: Annotated[User, Depends(require_any_permission("write:delivery_submit", "*"))],
) -> dict[str, Any]:
    try:
        delivery_svc.delete_delivery(delivery_id, user)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

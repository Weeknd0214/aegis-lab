"""Fleet map API routes."""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from as_platform.auth.deps import get_current_user, require_permission
from as_platform.config import AMAP_KEY, FLEET_MAP_ENABLED, MAP_TILE_PROVIDER, TBOX_INGEST_TOKEN
from as_platform.db.engine import get_db
from as_platform.db.models import User
from as_platform.fleet import service as fleet_svc
from as_platform.fleet.mock_seed import reseed_demo_fleet, seed_demo_fleet

router = APIRouter(tags=["fleet"])


class VehicleBody(BaseModel):
    plate_no: str
    tbox_device_id: str
    name: str | None = None
    team: str | None = None
    status: str | None = "active"


class VehiclePatchBody(BaseModel):
    plate_no: str | None = None
    tbox_device_id: str | None = None
    name: str | None = None
    team: str | None = None
    status: str | None = None


class TboxGpsBody(BaseModel):
    device_id: str
    lat: float
    lng: float
    ts: str | None = None
    speed_kmh: float | None = None
    heading: float | None = None
    plate_no: str | None = None
    run_signal: str | None = "active"
    engineer: str | None = None
    project: str | None = None
    batch: str | None = None


class TboxGpsBatchBody(BaseModel):
    points: list[TboxGpsBody] = Field(..., min_length=1, max_length=100)


def _check_fleet_enabled() -> None:
    if not FLEET_MAP_ENABLED:
        raise HTTPException(503, "车队地图功能未启用 (AS_FLEET_MAP_ENABLED)")


def _verify_tbox_token(x_tbox_token: str | None = None, authorization: str | None = None) -> None:
    token = (x_tbox_token or "").strip()
    if not token and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if not TBOX_INGEST_TOKEN:
        return
    if token != TBOX_INGEST_TOKEN:
        raise HTTPException(401, "T-Box Token 无效")


@router.get("/api/v1/fleet/map-config")
def fleet_map_config(_user: Annotated[User, Depends(require_permission("read:fleet"))]) -> dict[str, Any]:
    _check_fleet_enabled()
    tile_provider = MAP_TILE_PROVIDER if MAP_TILE_PROVIDER in ("gaode", "osm") else "gaode"
    return {
        "enabled": True,
        "provider": tile_provider,
        "tileProvider": tile_provider,
        "amapKey": AMAP_KEY or "",
        "pollIntervalSec": 5,
        "note": "GPS 为 WGS84，高德底图为 GCJ-02，演示轨迹可能有轻微偏移",
    }


@router.get("/api/v1/fleet/live")
def fleet_live(_user: Annotated[User, Depends(require_permission("read:fleet"))], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    _check_fleet_enabled()
    return fleet_svc.get_live_fleet(db)


@router.get("/api/v1/fleet/vehicles")
def fleet_vehicles(_user: Annotated[User, Depends(require_permission("read:fleet"))], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    _check_fleet_enabled()
    return {"items": fleet_svc.list_vehicles(db)}


@router.get("/api/v1/fleet/vehicles/{vehicle_id}")
def fleet_vehicle_get(
    vehicle_id: int,
    _user: Annotated[User, Depends(require_permission("read:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _check_fleet_enabled()
    item = fleet_svc.get_vehicle(db, vehicle_id)
    if not item:
        raise HTTPException(404, "车辆不存在")
    return item


@router.post("/api/v1/fleet/vehicles")
def fleet_vehicle_create(
    body: VehicleBody,
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _check_fleet_enabled()
    try:
        item = fleet_svc.create_vehicle(db, body.model_dump())
        db.commit()
        return {"ok": True, "vehicle": item}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/api/v1/fleet/vehicles/{vehicle_id}")
def fleet_vehicle_update(
    vehicle_id: int,
    body: VehiclePatchBody,
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _check_fleet_enabled()
    try:
        item = fleet_svc.update_vehicle(db, vehicle_id, body.model_dump(exclude_unset=True))
        db.commit()
        return {"ok": True, "vehicle": item}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/v1/fleet/vehicles/{vehicle_id}")
def fleet_vehicle_delete(
    vehicle_id: int,
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _check_fleet_enabled()
    try:
        fleet_svc.delete_vehicle(db, vehicle_id)
        db.commit()
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/v1/fleet/runs")
def fleet_runs(
    _user: Annotated[User, Depends(require_permission("read:fleet"))],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: int | None = None,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    _check_fleet_enabled()
    return fleet_svc.list_runs(db, vehicle_id=vehicle_id, status=status, offset=offset, limit=limit)


@router.get("/api/v1/fleet/runs/{run_id}")
def fleet_run_detail(run_id: int, _user: Annotated[User, Depends(require_permission("read:fleet"))], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    _check_fleet_enabled()
    detail = fleet_svc.get_run_detail(db, run_id)
    if not detail:
        raise HTTPException(404, "趟次不存在")
    return detail


@router.get("/api/v1/fleet/runs/{run_id}/track")
def fleet_run_track(run_id: int, _user: Annotated[User, Depends(require_permission("read:fleet"))], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    _check_fleet_enabled()
    return fleet_svc.get_run_track_geojson(db, run_id)


@router.get("/api/v1/fleet/summary")
def fleet_summary(_user: Annotated[User, Depends(require_permission("read:fleet"))], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    _check_fleet_enabled()
    return fleet_svc.fleet_summary(db)


@router.post("/api/v1/fleet/mock/seed")
def fleet_mock_seed(
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _check_fleet_enabled()
    created = seed_demo_fleet(db)
    db.commit()
    return {"ok": True, "created": created}


@router.post("/api/v1/fleet/mock/reseed")
def fleet_mock_reseed(
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """清空车队演示数据并重新注入（切换区域后使用）。"""
    _check_fleet_enabled()
    created = reseed_demo_fleet(db)
    db.commit()
    return {"ok": True, "created": created, "region": "changsha"}


@router.post("/api/v1/fleet/mock/tick")
def fleet_mock_tick(
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _check_fleet_enabled()
    n = fleet_svc.simulate_tick(db)
    db.commit()
    return {"ok": True, "advanced": n}


@router.post("/api/v1/fleet/runs/import-gpx")
async def fleet_import_gpx(
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: int = Form(...),
    file: UploadFile = File(...),
    note: str | None = Form(None),
) -> dict[str, Any]:
    _check_fleet_enabled()
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="ignore")
    try:
        result = fleet_svc.import_gpx_run(db, vehicle_id=vehicle_id, gpx_content=text, note=note)
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/v1/fleet/stream")
def fleet_stream(
    _user: Annotated[User, Depends(require_permission("read:fleet"))],
) -> StreamingResponse:
    """SSE：推送 fleet.gps 事件（需 Redis）。"""
    _check_fleet_enabled()
    from as_platform.redis.bus import get_redis

    def event_generator():
        r = get_redis()
        if not r:
            yield f"data: {json.dumps({'event': 'error', 'message': 'redis unavailable'}, ensure_ascii=False)}\n\n"
            return
        pubsub = r.pubsub()
        pubsub.subscribe("as:events")
        yield f"data: {json.dumps({'event': 'fleet.connected'}, ensure_ascii=False)}\n\n"
        while True:
            msg = pubsub.get_message(timeout=25)
            if msg is None:
                yield ": ping\n\n"
                continue
            if msg.get("type") != "message":
                continue
            raw = msg.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            if isinstance(raw, str) and "fleet." in raw:
                yield f"data: {raw}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/v1/tbox/gps")
def tbox_gps(
    body: TboxGpsBody,
    db: Annotated[Session, Depends(get_db)],
    x_tbox_token: Annotated[str | None, Header(alias="X-Tbox-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_fleet_enabled()
    _verify_tbox_token(x_tbox_token, authorization)
    try:
        fleet_svc.close_idle_runs(db)
        result = fleet_svc.ingest_tbox_gps(db, body.model_dump())
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/v1/tbox/gps/batch")
def tbox_gps_batch(
    body: TboxGpsBatchBody,
    db: Annotated[Session, Depends(get_db)],
    x_tbox_token: Annotated[str | None, Header(alias="X-Tbox-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _check_fleet_enabled()
    _verify_tbox_token(x_tbox_token, authorization)
    try:
        fleet_svc.close_idle_runs(db)
        result = fleet_svc.ingest_tbox_gps_batch(db, [p.model_dump() for p in body.points])
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/v1/fleet/runs/import-csv")
async def fleet_import_csv(
    _user: Annotated[User, Depends(require_permission("write:fleet"))],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: int = Form(...),
    file: UploadFile = File(...),
    note: str | None = Form(None),
    project: str | None = Form(None),
    batch: str | None = Form(None),
) -> dict[str, Any]:
    _check_fleet_enabled()
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="ignore")
    try:
        result = fleet_svc.import_csv_run(
            db,
            vehicle_id=vehicle_id,
            csv_content=text,
            note=note,
            project=project,
            batch=batch,
        )
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

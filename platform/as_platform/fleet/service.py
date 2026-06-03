"""Fleet map business logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from as_platform.db.models import (
    FleetCollectionRun,
    FleetRunMilestone,
    FleetTrackPoint,
    FleetVehicle,
)
from as_platform.fleet.geo import haversine_km, simplify_coords
from as_platform.fleet.mock_seed import ROUTES
from as_platform.redis.bus import publish

RUN_IDLE_TIMEOUT_MIN = 10


def _parse_ts(ts: str | datetime | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def get_vehicle_by_device(db: Session, device_id: str) -> FleetVehicle | None:
    return db.query(FleetVehicle).filter_by(tbox_device_id=device_id).first()


def get_active_run(db: Session, vehicle_id: int) -> FleetCollectionRun | None:
    return (
        db.query(FleetCollectionRun)
        .filter_by(vehicle_id=vehicle_id, status="active")
        .order_by(desc(FleetCollectionRun.id))
        .first()
    )


def recalc_run_mileage(db: Session, run_id: int) -> float:
    pts = (
        db.query(FleetTrackPoint)
        .filter_by(run_id=run_id)
        .order_by(FleetTrackPoint.ts.asc())
        .all()
    )
    total = 0.0
    prev = None
    for p in pts:
        if prev:
            total += haversine_km(prev[0], prev[1], p.lat, p.lng)
        prev = (p.lat, p.lng)
    run = db.get(FleetCollectionRun, run_id)
    if run:
        run.mileage_km = round(total, 3)
    return total


def _ensure_start_milestone(db: Session, run: FleetCollectionRun, lat: float, lng: float, ts: datetime) -> None:
    exists = db.query(FleetRunMilestone).filter_by(run_id=run.id, type="start").first()
    if exists:
        return
    db.add(FleetRunMilestone(run_id=run.id, type="start", name="出发", lat=lat, lng=lng, mileage_km=0.0, occurred_at=ts))


def _close_run(db: Session, run: FleetCollectionRun, lat: float, lng: float, ts: datetime) -> None:
    run.status = "ended"
    run.ended_at = ts
    recalc_run_mileage(db, run.id)
    end_ms = db.query(FleetRunMilestone).filter_by(run_id=run.id, type="end").first()
    if not end_ms:
        db.add(
            FleetRunMilestone(
                run_id=run.id,
                type="end",
                name="结束",
                lat=lat,
                lng=lng,
                mileage_km=run.mileage_km,
                occurred_at=ts,
            )
        )


def ingest_tbox_gps(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        raise ValueError("device_id 必填")
    lat = float(payload["lat"])
    lng = float(payload["lng"])
    ts = _parse_ts(payload.get("ts"))
    speed = float(payload["speed_kmh"]) if payload.get("speed_kmh") is not None else None
    heading = float(payload["heading"]) if payload.get("heading") is not None else None
    run_signal = str(payload.get("run_signal") or "active").lower()
    plate_no = str(payload.get("plate_no") or "").strip()

    vehicle = get_vehicle_by_device(db, device_id)
    if not vehicle:
        vehicle = FleetVehicle(
            plate_no=plate_no or device_id,
            tbox_device_id=device_id,
            name=plate_no or device_id,
            team="T-Box",
            status="active",
            online=True,
        )
        db.add(vehicle)
        db.flush()

    vehicle.last_lat = lat
    vehicle.last_lng = lng
    vehicle.last_speed_kmh = speed
    vehicle.last_ts = ts
    vehicle.online = True

    run = get_active_run(db, vehicle.id)
    if run_signal in ("idle", "off", "end", "stopped"):
        if run:
            _close_run(db, run, lat, lng, ts)
        vehicle.online = False
        db.flush()
        publish("fleet.gps", {"vehicle_id": vehicle.id, "device_id": device_id, "lat": lat, "lng": lng})
        return {"ok": True, "vehicle": vehicle.to_dict(), "run": run.to_dict() if run else None, "closed": True}

    if not run:
        run_no = f"{device_id}-{ts.strftime('%Y%m%d%H%M')}"
        run = FleetCollectionRun(
            vehicle_id=vehicle.id,
            run_no=run_no,
            engineer=payload.get("engineer"),
            project=payload.get("project"),
            batch=payload.get("batch"),
            started_at=ts,
            status="active",
            source="tbox",
        )
        db.add(run)
        db.flush()
        _ensure_start_milestone(db, run, lat, lng, ts)

    prev = (
        db.query(FleetTrackPoint)
        .filter_by(run_id=run.id)
        .order_by(desc(FleetTrackPoint.ts))
        .first()
    )
    seg = 0.0
    if prev:
        seg = haversine_km(prev.lat, prev.lng, lat, lng)
    db.add(FleetTrackPoint(run_id=run.id, ts=ts, lat=lat, lng=lng, speed_kmh=speed, heading=heading))
    run.mileage_km = round((run.mileage_km or 0.0) + seg, 3)
    db.flush()
    publish("fleet.gps", {"vehicle_id": vehicle.id, "run_id": run.id, "lat": lat, "lng": lng})
    return {"ok": True, "vehicle": vehicle.to_dict(), "run": run.to_dict()}


def list_vehicles(db: Session) -> list[dict]:
    return [v.to_dict() for v in db.query(FleetVehicle).order_by(FleetVehicle.id).all()]


def get_vehicle(db: Session, vehicle_id: int) -> dict | None:
    v = db.get(FleetVehicle, vehicle_id)
    return v.to_dict() if v else None


def create_vehicle(db: Session, data: dict[str, Any]) -> dict:
    device_id = str(data.get("tbox_device_id") or "").strip()
    plate_no = str(data.get("plate_no") or "").strip()
    if not device_id:
        raise ValueError("tbox_device_id 必填")
    if not plate_no:
        raise ValueError("plate_no 必填")
    if get_vehicle_by_device(db, device_id):
        raise ValueError(f"设备 ID 已存在: {device_id}")
    v = FleetVehicle(
        plate_no=plate_no,
        tbox_device_id=device_id,
        name=str(data.get("name") or plate_no).strip(),
        team=str(data.get("team") or "").strip() or None,
        status=str(data.get("status") or "active").strip() or "active",
        online=False,
    )
    db.add(v)
    db.flush()
    return v.to_dict()


def update_vehicle(db: Session, vehicle_id: int, data: dict[str, Any]) -> dict:
    v = db.get(FleetVehicle, vehicle_id)
    if not v:
        raise ValueError("车辆不存在")
    if "tbox_device_id" in data and data["tbox_device_id"]:
        new_dev = str(data["tbox_device_id"]).strip()
        other = get_vehicle_by_device(db, new_dev)
        if other and other.id != vehicle_id:
            raise ValueError(f"设备 ID 已被占用: {new_dev}")
        v.tbox_device_id = new_dev
    if "plate_no" in data and data["plate_no"]:
        v.plate_no = str(data["plate_no"]).strip()
    if "name" in data:
        v.name = str(data["name"] or v.plate_no).strip()
    if "team" in data:
        v.team = str(data["team"]).strip() or None
    if "status" in data and data["status"]:
        v.status = str(data["status"]).strip()
    db.flush()
    return v.to_dict()


def delete_vehicle(db: Session, vehicle_id: int) -> None:
    v = db.get(FleetVehicle, vehicle_id)
    if not v:
        raise ValueError("车辆不存在")
    if get_active_run(db, vehicle_id):
        raise ValueError("该车有进行中的趟次，请先结束趟次后再删除")
    db.delete(v)


def _run_duration_sec(run: FleetCollectionRun) -> int:
    if not run.started_at:
        return 0
    end = run.ended_at
    if end is None and run.status == "active":
        end = datetime.now(timezone.utc)
    if end is None:
        return 0
    return max(0, int((end - run.started_at).total_seconds()))


def list_runs(
    db: Session,
    vehicle_id: int | None = None,
    status: str | None = None,
    *,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    q = db.query(FleetCollectionRun).order_by(desc(FleetCollectionRun.started_at))
    if vehicle_id:
        q = q.filter_by(vehicle_id=vehicle_id)
    if status:
        q = q.filter_by(status=status)
    total = q.count()
    rows = q.offset(max(0, offset)).limit(max(1, limit)).all()
    out: list[dict] = []
    for r in rows:
        d = r.to_dict()
        d["point_count"] = db.query(FleetTrackPoint).filter_by(run_id=r.id).count()
        d["milestone_count"] = db.query(FleetRunMilestone).filter_by(run_id=r.id).count()
        d["duration_sec"] = _run_duration_sec(r)
        out.append(d)
    return {"items": out, "total": total, "offset": offset, "limit": limit}


def get_run_detail(db: Session, run_id: int) -> dict | None:
    run = db.get(FleetCollectionRun, run_id)
    if not run:
        return None
    vehicle = db.get(FleetVehicle, run.vehicle_id)
    milestones = (
        db.query(FleetRunMilestone).filter_by(run_id=run_id).order_by(FleetRunMilestone.occurred_at.asc()).all()
    )
    return {
        "run": run.to_dict(),
        "vehicle": vehicle.to_dict() if vehicle else None,
        "milestones": [m.to_dict() for m in milestones],
    }


def close_idle_runs(db: Session) -> int:
    """无 GPS 超过 RUN_IDLE_TIMEOUT_MIN 的 active 趟次自动结束。"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=RUN_IDLE_TIMEOUT_MIN)
    closed = 0
    for run in db.query(FleetCollectionRun).filter_by(status="active").all():
        vehicle = db.get(FleetVehicle, run.vehicle_id)
        last_ts = vehicle.last_ts if vehicle else None
        if not last_ts or last_ts >= cutoff:
            continue
        lat = float(vehicle.last_lat or 0) if vehicle else 0.0
        lng = float(vehicle.last_lng or 0) if vehicle else 0.0
        _close_run(db, run, lat, lng, datetime.now(timezone.utc))
        if vehicle:
            vehicle.online = False
        closed += 1
    return closed


def ingest_tbox_gps_batch(db: Session, points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        raise ValueError("points 不能为空")
    if len(points) > 100:
        raise ValueError("单次最多 100 个点")
    results: list[dict[str, Any]] = []
    for payload in points:
        results.append(ingest_tbox_gps(db, payload))
    return {"ok": True, "count": len(results), "last": results[-1] if results else None}


def _parse_csv_track(content: str) -> list[tuple[float, float, datetime | None]]:
    import csv
    from io import StringIO

    rows = list(csv.reader(StringIO(content.strip())))
    if not rows:
        return []
    start = 0
    header = [c.strip().lower() for c in rows[0]]
    if any(h in header for h in ("lat", "lng", "lon", "latitude", "longitude")):
        start = 1
    points: list[tuple[float, float, datetime | None]] = []
    for row in rows[start:]:
        if len(row) < 2:
            continue
        try:
            if start and len(header) >= 2:
                idx = {h: i for i, h in enumerate(header)}
                lat_i = idx.get("lat", idx.get("latitude", 0))
                lng_i = idx.get("lng", idx.get("lon", idx.get("longitude", 1)))
                lat = float(row[lat_i])
                lng = float(row[lng_i])
                ts_i = idx.get("ts") or idx.get("time")
                ts = _parse_ts(row[ts_i]) if ts_i is not None and ts_i < len(row) else None
            else:
                lat = float(row[0])
                lng = float(row[1])
                ts = _parse_ts(row[2]) if len(row) > 2 and row[2].strip() else None
            points.append((lat, lng, ts))
        except (ValueError, IndexError):
            continue
    return points


def import_csv_run(db: Session, *, vehicle_id: int, csv_content: str, note: str | None = None, project: str | None = None, batch: str | None = None) -> dict[str, Any]:
    vehicle = db.get(FleetVehicle, vehicle_id)
    if not vehicle:
        raise ValueError("车辆不存在")
    pts = _parse_csv_track(csv_content)
    if len(pts) < 2:
        raise ValueError("CSV 轨迹点不足")
    active = get_active_run(db, vehicle_id)
    if active:
        _close_run(db, active, pts[0][0], pts[0][1], pts[0][2] or datetime.now(timezone.utc))
    start_ts = pts[0][2] or datetime.now(timezone.utc)
    run_no = f"csv-{vehicle_id}-{int(start_ts.timestamp())}"
    run = FleetCollectionRun(
        vehicle_id=vehicle_id,
        run_no=run_no,
        status="ended",
        source="csv",
        note=note,
        project=project,
        batch=batch,
        started_at=start_ts,
        ended_at=pts[-1][2] or datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    for lat, lng, ts in pts:
        t = ts or start_ts
        db.add(FleetTrackPoint(run_id=run.id, lat=lat, lng=lng, ts=t, speed_kmh=0.0))
    _ensure_start_milestone(db, run, pts[0][0], pts[0][1], start_ts)
    _close_run(db, run, pts[-1][0], pts[-1][1], pts[-1][2] or datetime.now(timezone.utc))
    recalc_run_mileage(db, run.id)
    return {"ok": True, "run_id": run.id, "point_count": len(pts), "mileage_km": run.mileage_km}


def get_live_fleet(db: Session) -> dict[str, Any]:
    close_idle_runs(db)
    vehicles = db.query(FleetVehicle).order_by(FleetVehicle.id).all()
    items = []
    for v in vehicles:
        active = get_active_run(db, v.id)
        items.append(
            {
                **v.to_dict(),
                "active_run_id": active.id if active else None,
                "active_mileage_km": active.mileage_km if active else None,
                "active_run_no": active.run_no if active else None,
            }
        )
    active_runs = db.query(FleetCollectionRun).filter_by(status="active").count()
    total_km = sum(r.mileage_km or 0.0 for r in db.query(FleetCollectionRun).all())
    return {
        "vehicles": items,
        "stats": {
            "vehicle_count": len(vehicles),
            "online_count": sum(1 for v in vehicles if v.online),
            "active_runs": active_runs,
            "total_mileage_km": round(total_km, 2),
        },
        "mock": True,
    }


def get_run_track_geojson(db: Session, run_id: int, max_points: int = 5000) -> dict:
    pts = (
        db.query(FleetTrackPoint)
        .filter_by(run_id=run_id)
        .order_by(FleetTrackPoint.ts.asc())
        .all()
    )
    coords = [[p.lng, p.lat] for p in pts]
    coords = simplify_coords(coords, max_points)
    milestones = db.query(FleetRunMilestone).filter_by(run_id=run_id).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"kind": "track", "run_id": run_id, "point_count": len(pts)},
                "geometry": {"type": "LineString", "coordinates": coords},
            },
            *[
                {
                    "type": "Feature",
                    "properties": {"kind": "milestone", **m.to_dict()},
                    "geometry": {"type": "Point", "coordinates": [m.lng, m.lat]},
                }
                for m in milestones
            ],
        ],
        "points": [p.to_dict() for p in pts[-200:]],
    }


def fleet_summary(db: Session) -> dict:
    runs = db.query(FleetCollectionRun).all()
    by_vehicle: dict[int, float] = {}
    for r in runs:
        by_vehicle[r.vehicle_id] = by_vehicle.get(r.vehicle_id, 0.0) + (r.mileage_km or 0.0)
    vehicles = {v.id: v for v in db.query(FleetVehicle).all()}
    per_vehicle = [
        {
            "vehicle_id": vid,
            "plate_no": vehicles[vid].plate_no if vid in vehicles else str(vid),
            "mileage_km": round(km, 2),
        }
        for vid, km in by_vehicle.items()
    ]
    return {
        "total_runs": len(runs),
        "active_runs": sum(1 for r in runs if r.status == "active"),
        "total_mileage_km": round(sum(r.mileage_km or 0.0 for r in runs), 2),
        "per_vehicle": per_vehicle,
    }


def simulate_tick(db: Session) -> int:
    """Advance mock vehicles along ROUTES (demo)."""
    n = 0
    now = datetime.now(timezone.utc)
    for v in db.query(FleetVehicle).all():
        meta = v.meta()
        route_key = meta.get("sim_route") or v.tbox_device_id
        coords = ROUTES.get(route_key)
        if not coords:
            continue
        run = get_active_run(db, v.id)
        if not run:
            continue
        idx = int(meta.get("sim_index", 0))
        direction = int(meta.get("sim_dir", 1))
        next_idx = idx + direction
        if next_idx >= len(coords):
            next_idx = len(coords) - 2
            direction = -1
        elif next_idx < 0:
            next_idx = 1
            direction = 1
        lat, lng = coords[next_idx]
        payload = {
            "device_id": v.tbox_device_id,
            "lat": lat,
            "lng": lng,
            "ts": now.isoformat(),
            "speed_kmh": 38.0 + (next_idx % 4),
            "run_signal": "active",
        }
        ingest_tbox_gps(db, payload)
        v.set_meta({**meta, "sim_index": next_idx, "sim_route": route_key, "sim_dir": direction})
        n += 1
    return n


def _parse_gpx_points(content: str) -> list[tuple[float, float, datetime | None]]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(content)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    points: list[tuple[float, float, datetime | None]] = []
    for trkpt in root.iter(f"{ns}trkpt"):
        lat_s = trkpt.get("lat")
        lon_s = trkpt.get("lon")
        if lat_s is None or lon_s is None:
            continue
        ts_el = trkpt.find(f"{ns}time")
        ts = _parse_ts(ts_el.text) if ts_el is not None and ts_el.text else None
        points.append((float(lat_s), float(lon_s), ts))
    return points


def import_gpx_run(db: Session, *, vehicle_id: int, gpx_content: str, note: str | None = None) -> dict[str, Any]:
    vehicle = db.get(FleetVehicle, vehicle_id)
    if not vehicle:
        raise ValueError("车辆不存在")
    pts = _parse_gpx_points(gpx_content)
    if len(pts) < 2:
        raise ValueError("GPX 轨迹点不足")
    active = get_active_run(db, vehicle_id)
    if active:
        _close_run(db, active, pts[0][0], pts[0][1], pts[0][2] or datetime.now(timezone.utc))
    start_ts = pts[0][2] or datetime.now(timezone.utc)
    run_no = f"gpx-{vehicle_id}-{int(start_ts.timestamp())}"
    run = FleetCollectionRun(
        vehicle_id=vehicle_id,
        run_no=run_no,
        status="ended",
        source="gpx",
        note=note,
        started_at=start_ts,
        ended_at=pts[-1][2] or datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    prev = None
    for lat, lng, ts in pts:
        t = ts or start_ts
        db.add(FleetTrackPoint(run_id=run.id, lat=lat, lng=lng, ts=t, speed_kmh=0.0))
        if prev is None:
            _ensure_start_milestone(db, run, lat, lng, t)
        prev = (lat, lng)
    end_ts = pts[-1][2] or datetime.now(timezone.utc)
    _close_run(db, run, pts[-1][0], pts[-1][1], end_ts)
    recalc_run_mileage(db, run.id)
    return {"ok": True, "run_id": run.id, "point_count": len(pts), "mileage_km": run.mileage_km}

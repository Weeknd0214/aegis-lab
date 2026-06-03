"""Demo fleet seed data (Changsha area, curved paths)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from as_platform.db.models import (
    FleetCollectionRun,
    FleetRunMilestone,
    FleetTrackPoint,
    FleetVehicle,
)
from as_platform.fleet.geo import haversine_km


def _catmull_rom_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    t2, t3 = t * t, t * t * t
    lat = 0.5 * (
        (2 * p1[0])
        + (-p0[0] + p2[0]) * t
        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
    )
    lng = 0.5 * (
        (2 * p1[1])
        + (-p0[1] + p2[1]) * t
        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
    )
    return (lat, lng)


def build_curved_route(anchors: list[tuple[float, float]], steps_per_seg: int = 24) -> list[tuple[float, float]]:
    """Catmull-Rom 样条密点，地图折线呈弯道。"""
    if len(anchors) < 2:
        return list(anchors)
    pts = [anchors[0], *anchors, anchors[-1]]
    path: list[tuple[float, float]] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(steps_per_seg):
            t = j / steps_per_seg
            path.append(_catmull_rom_point(p0, p1, p2, p3, t))
    path.append(anchors[-1])
    return path


def _wiggle(path: list[tuple[float, float]], amp: float = 0.004) -> list[tuple[float, float]]:
    """叠加轻微蛇形偏移，避免视觉上像直线。"""
    out: list[tuple[float, float]] = []
    for i, (lat, lng) in enumerate(path):
        w = math.sin(i * 0.35) * amp
        out.append((lat + w, lng - w * 0.6))
    return out


# 长沙：锚点刻意折线（之字形 / 弧形），再样条平滑
_ANCHORS: dict[str, list[tuple[float, float]]] = {
    "TBOX-001": [
        (28.172, 112.902),
        (28.188, 112.918),
        (28.205, 112.908),
        (28.222, 112.928),
        (28.238, 112.948),
        (28.252, 112.978),
        (28.248, 113.012),
        (28.235, 113.042),
        (28.218, 113.058),
        (28.202, 113.048),
    ],
    "TBOX-002": [
        (28.278, 112.948),
        (28.270, 112.972),
        (28.255, 113.002),
        (28.238, 113.028),
        (28.218, 113.048),
        (28.202, 113.038),
        (28.198, 113.008),
        (28.208, 112.978),
        (28.225, 112.958),
        (28.248, 112.952),
    ],
    "TBOX-003": [
        (28.212, 112.918),
        (28.225, 112.938),
        (28.242, 112.928),
        (28.258, 112.948),
        (28.272, 112.972),
        (28.268, 113.002),
        (28.252, 113.022),
        (28.232, 113.028),
        (28.215, 113.012),
        (28.208, 112.982),
        (28.212, 112.918),
    ],
}

ROUTES: dict[str, list[tuple[float, float]]] = {
    k: _wiggle(build_curved_route(v, steps_per_seg=28), amp=0.003)
    for k, v in _ANCHORS.items()
}

VEHICLES = [
    ("TBOX-001", "湘A·采集01", "岳麓采集车 A", "数据部"),
    ("TBOX-002", "湘A·采集02", "开福采集车 B", "数据部"),
    ("TBOX-003", "湘A·采集03", "天心采集车 C", "数据部"),
]


def _add_points(db: Session, run_id: int, coords: list[tuple[float, float]], start: datetime, interval_sec: int = 12) -> float:
    mileage = 0.0
    prev = None
    for i, (lat, lng) in enumerate(coords):
        ts = start + timedelta(seconds=i * interval_sec)
        speed = 35.0 + (i % 5) * 3.0
        pt = FleetTrackPoint(run_id=run_id, ts=ts, lat=lat, lng=lng, speed_kmh=speed, heading=float(i * 10 % 360))
        db.add(pt)
        if prev:
            mileage += haversine_km(prev[0], prev[1], lat, lng)
        prev = (lat, lng)
    return mileage


def clear_demo_fleet(db: Session) -> None:
    db.query(FleetRunMilestone).delete()
    db.query(FleetTrackPoint).delete()
    db.query(FleetCollectionRun).delete()
    db.query(FleetVehicle).delete()
    db.flush()


def seed_demo_fleet(db: Session) -> bool:
    if db.query(FleetVehicle).count() > 0:
        return False
    now = datetime.now(timezone.utc)
    for device_id, plate, name, team in VEHICLES:
        coords = ROUTES[device_id]
        v = FleetVehicle(
            plate_no=plate,
            tbox_device_id=device_id,
            name=name,
            team=team,
            status="active",
            online=True,
            last_lat=coords[-1][0],
            last_lng=coords[-1][1],
            last_speed_kmh=42.0,
            last_ts=now,
        )
        v.set_meta({"sim_index": 0, "sim_route": device_id, "sim_dir": 1})
        db.add(v)
        db.flush()

        ended_start = now - timedelta(hours=6)
        ended = FleetCollectionRun(
            vehicle_id=v.id,
            run_no=f"{device_id}-{(ended_start.strftime('%Y%m%d'))}-01",
            engineer="陈工",
            project="dms",
            batch="demo_batch_01",
            started_at=ended_start,
            ended_at=ended_start + timedelta(hours=2),
            status="ended",
            source="mock",
            note="演示历史趟次（长沙弯道）",
        )
        db.add(ended)
        db.flush()
        em = _add_points(db, ended.id, coords, ended_start)
        ended.mileage_km = round(em, 3)
        db.add(FleetRunMilestone(run_id=ended.id, type="start", name="出发", lat=coords[0][0], lng=coords[0][1], mileage_km=0.0, occurred_at=ended_start))
        db.add(FleetRunMilestone(run_id=ended.id, type="end", name="结束", lat=coords[-1][0], lng=coords[-1][1], mileage_km=ended.mileage_km, occurred_at=ended.ended_at))
        db.add(FleetRunMilestone(run_id=ended.id, type="data_site", name="采集点-1", lat=coords[len(coords)//2][0], lng=coords[len(coords)//2][1], mileage_km=ended.mileage_km / 2, occurred_at=ended_start + timedelta(hours=1)))

        active_start = now - timedelta(minutes=45)
        active = FleetCollectionRun(
            vehicle_id=v.id,
            run_no=f"{device_id}-{now.strftime('%Y%m%d')}-live",
            engineer="李工",
            project="lane",
            batch="demo_batch_live",
            started_at=active_start,
            status="active",
            source="mock",
            note="演示进行中趟次（长沙弯道）",
        )
        db.add(active)
        db.flush()
        # 进行中趟次也写入完整弯道轨迹（不再只种前半段）
        am = _add_points(db, active.id, coords, active_start)
        active.mileage_km = round(am, 3)
        v.last_lat = coords[-1][0]
        v.last_lng = coords[-1][1]
        v.last_ts = active_start + timedelta(seconds=(len(coords) - 1) * 12)
        v.set_meta({"sim_index": len(coords) - 1, "sim_route": device_id, "sim_dir": -1})
        db.add(FleetRunMilestone(run_id=active.id, type="start", name="出发", lat=coords[0][0], lng=coords[0][1], mileage_km=0.0, occurred_at=active_start))
    db.flush()
    return True


def reseed_demo_fleet(db: Session) -> bool:
    """清空并重新注入长沙演示数据。"""
    clear_demo_fleet(db)
    return seed_demo_fleet(db)

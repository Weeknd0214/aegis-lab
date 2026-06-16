"""Cuboid 16pt + K → MOON-3D 3D detection fields (MVP fit)."""
from __future__ import annotations

import math
from typing import Any

# Default WLH priors in meters (width, length, height) — BK2/MOON convention
CLASS_PRIORS: dict[str, tuple[float, float, float]] = {
    "pedestrian": (0.6, 0.6, 1.7),
    "car": (1.8, 4.5, 1.5),
    "truck": (2.5, 8.0, 3.0),
    "bus": (2.5, 10.0, 3.2),
    "motorcycle": (0.8, 2.0, 1.5),
    "tricycle": (1.2, 2.5, 1.8),
    "traffic cone": (0.4, 0.4, 0.8),
}


def cuboid_points_to_box2d(points: list[float]) -> list[float] | None:
    if len(points) < 16:
        return None
    xs = [float(points[i]) for i in range(0, 16, 2)]
    ys = [float(points[i]) for i in range(1, 16, 2)]
    return [min(xs), min(ys), max(xs), max(ys)]


def _project_point(x: float, y: float, z: float, K: list[list[float]]) -> tuple[float, float]:
    fx, fy = float(K[0][0]), float(K[1][1])
    cx, cy = float(K[0][2]), float(K[1][2])
    if z <= 0.01:
        z = 0.01
    u = fx * x / z + cx
    v = fy * y / z + cy
    return u, v


def _reproj_error(center, wlh, K, points2d) -> float:
    cx, cy, cz = center
    w, l, h = wlh
    # 8 corners in object frame (simplified axis-aligned box, no rotation MVP)
    corners = [
        (-l / 2, -w / 2, -h / 2), (l / 2, -w / 2, -h / 2),
        (l / 2, w / 2, -h / 2), (-l / 2, w / 2, -h / 2),
        (-l / 2, -w / 2, h / 2), (l / 2, -w / 2, h / 2),
        (l / 2, w / 2, h / 2), (-l / 2, w / 2, h / 2),
    ]
    # camera: x right, y down, z forward — object x forward, y left, z up
    err = 0.0
    for i, (ox, oy, oz) in enumerate(corners):
        cam_x = -oy
        cam_y = -oz
        cam_z = ox + cz
        u, v = _project_point(cam_x, cam_y, cam_z, K)
        px = points2d[i * 2]
        py = points2d[i * 2 + 1]
        err += (u - px) ** 2 + (v - py) ** 2
    return err / max(len(corners), 1)


def fit_cuboid_detection(
    points: list[float],
    K: list[list[float]],
    class_name: str,
) -> dict[str, Any]:
    """Fit 3D box from 16 cuboid points. Returns fields to merge into detection."""
    box2d = cuboid_points_to_box2d(points)
    if not box2d or not K:
        return {"fit_ok": False, "fit_error": "missing points or K"}

    w0, l0, h0 = CLASS_PRIORS.get(class_name.lower(), CLASS_PRIORS.get(class_name, (1.8, 4.0, 1.5)))
    if class_name.lower() not in {k.lower() for k in CLASS_PRIORS}:
        for k, v in CLASS_PRIORS.items():
            if k.lower() == class_name.lower():
                w0, l0, h0 = v
                break

    fx = float(K[0][0])
    fy = float(K[1][1])
    cy = float(K[1][2])
    y1, y2 = box2d[1], box2d[3]
    pix_h = max(y2 - y1, 1.0)
    # depth from pinhole: h_pix = fy * H / Z
    z_est = fy * h0 / pix_h
    x1, x2 = box2d[0], box2d[2]
    u_c = (x1 + x2) / 2.0
    cx_cam = (u_c - float(K[0][2])) * z_est / fx

    # grid search depth / center for min reprojection error
    best_err = float("inf")
    best = (cx_cam, 0.0, z_est, w0, l0, h0)
    for dz in (-0.3, -0.15, 0, 0.15, 0.3):
        for dy in (-0.5, 0, 0.5):
            z = max(z_est + dz * z_est, 1.0)
            cx = cx_cam + dy
            err = _reproj_error((cx, 0.0, z), (w0, l0, h0), K, points)
            if err < best_err:
                best_err = err
                best = (cx, 0.0, z, w0, l0, h0)

    cx, cy, cz, w, l, h = best
    # OpenCV camera: x right, y down, z forward
    center_3d = [float(cx), float(cy), float(cz)]
    dimensions_wlh = [float(w), float(l), float(h)]
    rot_y = 0.0
    qw = math.cos(rot_y / 2)
    qy = math.sin(rot_y / 2)
    quaternion_wxyz = [float(qw), 0.0, float(qy), 0.0]

    fit_ok = best_err < 50000.0  # pixel^2 threshold MVP
    return {
        "center_3d": center_3d,
        "dimensions_wlh": dimensions_wlh,
        "quaternion_wxyz": quaternion_wxyz,
        "rotation_y": rot_y,
        "fit_ok": fit_ok,
        "fit_error": float(best_err),
        "box2d_xyxy": box2d,
    }


def fit_quaternion_json_file(data: dict[str, Any]) -> dict[str, Any]:
    K = data.get("K")
    if not K:
        return data
    out_dets = []
    for det in data.get("detections") or []:
        det = dict(det)
        if det.get("fit_ok"):
            out_dets.append(det)
            continue
        # recover points from box2d if no cuboid points stored — skip 3D
        class_name = str(det.get("class_name") or "car")
        box = det.get("box2d_xyxy")
        if not box or len(box) < 4:
            out_dets.append(det)
            continue
        # synthetic 16pt from AABB (degenerate but allows fit attempt)
        x1, y1, x2, y2 = box[:4]
        pts = [x1, y1, x2, y1, x1, y2, x2, y2, x1, y1, x2, y1, x1, y2, x2, y2]
        fitted = fit_cuboid_detection(pts, K, class_name)
        det.update({k: v for k, v in fitted.items() if k != "box2d_xyxy"})
        out_dets.append(det)
    data = dict(data)
    data["detections"] = out_dets
    data["num_detections"] = len(out_dets)
    return data

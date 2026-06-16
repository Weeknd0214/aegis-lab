"""Batch-level cuboid 3D fit for quaternion_json."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _task_id_for_image(image_path: Path, batch_dir: Path) -> str:
    try:
        rel = image_path.relative_to(batch_dir)
        stem = rel.as_posix()
    except ValueError:
        stem = image_path.name
    return hashlib.sha256(stem.encode()).hexdigest()[:16]


def _load_ls_cuboid_points(batch_dir: Path, stem: str) -> list[list[float]]:
    ann_dir = batch_dir / "labels" / "ls_annotations"
    if not ann_dir.is_dir():
        return []
    for p in ann_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        img = str(data.get("image") or "")
        if stem in img or p.stem:
            regions = data.get("result") or []
            pts_list = []
            for r in regions:
                if r.get("type") != "cuboid":
                    continue
                pts = list(r.get("points") or [])
                if len(pts) >= 16:
                    pts_list.append(pts[:16])
            if pts_list:
                return pts_list
    return []


def fit_batch(batch_dir: Path) -> dict[str, Any]:
    from algorithms.adas_mono3d.fit_cuboid import fit_cuboid_detection

    batch_dir = batch_dir.resolve()
    qdir = batch_dir / "labels" / "quaternion_json"
    if not qdir.is_dir():
        raise ValueError(f"missing {qdir}")

    updated = 0
    fit_ok = 0
    total = 0
    for p in sorted(qdir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        K = data.get("K")
        if not K:
            continue
        stem = data.get("image_stem") or p.stem
        cuboid_pts_list = _load_ls_cuboid_points(batch_dir, stem)
        new_dets = []
        for i, det in enumerate(data.get("detections") or []):
            det = dict(det)
            if det.get("fit_ok"):
                new_dets.append(det)
                total += 1
                fit_ok += 1
                continue
            class_name = str(det.get("class_name") or "car")
            points = cuboid_pts_list[i] if i < len(cuboid_pts_list) else None
            if not points:
                box = det.get("box2d_xyxy") or []
                if len(box) >= 4:
                    x1, y1, x2, y2 = box[:4]
                    points = [x1, y1, x2, y1, x1, y2, x2, y2, x1, y1, x2, y1, x1, y2, x2, y2]
            if points:
                fitted = fit_cuboid_detection(points, K, class_name)
                det.update({k: v for k, v in fitted.items() if k != "box2d_xyxy" or "box2d_xyxy" not in det})
            new_dets.append(det)
            total += 1
            if det.get("fit_ok"):
                fit_ok += 1
        data["detections"] = new_dets
        data["num_detections"] = len(new_dets)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1

    return {
        "updated_files": updated,
        "detections": total,
        "fit_ok": fit_ok,
        "fit_ok_ratio": fit_ok / max(total, 1),
    }

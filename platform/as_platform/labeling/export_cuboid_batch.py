"""ls_annotations cuboid → labels/quaternion_json/*.json（ADAS MOON-3D 兼容格式）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from as_platform.labeling.class_map import build_class_map, load_adas_class_names
from as_platform.labeling.format_converter import cuboid_item_to_detection

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}
ANNOTATIONS_DIRNAME = "ls_annotations"


def _load_cuboid_class_map() -> dict[str, int]:
    return build_class_map(load_adas_class_names())


def _task_id_for_image(image_path: Path, batch_dir: Path) -> str:
    try:
        rel = image_path.relative_to(batch_dir)
        stem = rel.as_posix()
    except ValueError:
        stem = image_path.name
    return hashlib.sha256(stem.encode()).hexdigest()[:16]


def _iter_batch_images(batch_dir: Path) -> list[Path]:
    if not batch_dir.is_dir():
        return []
    candidates: list[Path] = []
    search_roots = [batch_dir / "images", batch_dir / "images" / "train", batch_dir]
    seen: set[str] = set()
    for root in search_roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in IMG_EXTS:
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(p.resolve())
    return candidates


def _extract_result_regions(data: dict[str, Any]) -> list[dict[str, Any]]:
    result = data.get("result")
    if isinstance(result, list) and result:
        return result
    annotations = data.get("annotations")
    if isinstance(annotations, list) and annotations:
        first = annotations[0]
        if isinstance(first, dict) and isinstance(first.get("result"), list):
            return first["result"]
    return []


def _find_calib(batch_dir: Path) -> tuple[Path | None, list[list[float]] | None, list[int] | None]:
    calib_dir = batch_dir / "calib"
    if not calib_dir.is_dir():
        return None, None, None
    yaml_files = sorted(calib_dir.glob("*.yaml")) + sorted(calib_dir.glob("*.yml"))
    if not yaml_files:
        return None, None, None
    path = yaml_files[0]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return path, None, None
    K = data.get("K")
    image_size = data.get("image_size")
    if K and isinstance(K, list) and len(K) == 3:
        return path, K, list(image_size) if image_size else None
    fx = data.get("fx")
    fy = data.get("fy")
    cx = data.get("cx")
    cy = data.get("cy")
    if fx is not None and fy is not None and cx is not None and cy is not None:
        K = [[float(fx), 0.0, float(cx)], [0.0, float(fy), float(cy)], [0.0, 0.0, 1.0]]
        return path, K, list(image_size) if image_size else None
    return path, None, list(image_size) if image_size else None


def _resolve_image_for_ann(data: dict[str, Any], batch_dir: Path, task_id: str) -> Path | None:
    image_name = data.get("image")
    if image_name:
        for root in (batch_dir / "images", batch_dir):
            candidate = root / str(image_name)
            if candidate.is_file():
                return candidate
            for p in root.rglob(str(image_name)):
                if p.is_file():
                    return p
    for image_path in _iter_batch_images(batch_dir):
        if _task_id_for_image(image_path, batch_dir) == task_id:
            return image_path
    return None


def export_batch(batch_dir: Path) -> dict[str, Any]:
    """导出 cuboid ls_annotations → quaternion_json。"""
    batch_dir = batch_dir.resolve()
    class_map = _load_cuboid_class_map()
    calib_path, K, calib_size = _find_calib(batch_dir)
    ann_dir = batch_dir / "labels" / ANNOTATIONS_DIRNAME
    out_dir = batch_dir / "labels" / "quaternion_json"
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped_empty = 0
    missing_ann = 0

    for ann_path in sorted(ann_dir.glob("*.json")):
        task_id = ann_path.stem
        try:
            data = json.loads(ann_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing_ann += 1
            continue
        regions = _extract_result_regions(data)
        cuboids = [r for r in regions if r.get("type") == "cuboid"]
        if not cuboids:
            skipped_empty += 1
            continue

        image_path = _resolve_image_for_ann(data, batch_dir, task_id)
        if not image_path:
            missing_ann += 1
            continue

        detections: list[dict[str, Any]] = []
        for item in cuboids:
            det = cuboid_item_to_detection(item, class_map, K=K)
            if det:
                detections.append(det)
        if not detections:
            skipped_empty += 1
            continue

        img_w = int((cuboids[0].get("original_width") or (calib_size or [1920, 1080])[0]))
        img_h = int((cuboids[0].get("original_height") or (calib_size or [1920, 1080])[1]))

        payload: dict[str, Any] = {
            "image": str(image_path),
            "image_stem": image_path.stem,
            "image_size": [img_w, img_h],
            "coordinate_frame": "opencv_camera",
            "boxes3d_format": "center_3d + dimensions_wlh + quaternion_wxyz",
            "text_prompts": load_adas_class_names(),
            "num_detections": len(detections),
            "detections": detections,
        }
        if K:
            payload["K"] = K
            payload["k_source"] = calib_path.name if calib_path else "fixed_calib"
        else:
            payload["k_source"] = "missing_calib"

        out_path = out_dir / f"{image_path.stem}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1

    return {
        "written": written,
        "skipped_empty": skipped_empty,
        "missing_ann": missing_ann,
        "missing_calib": calib_path is None or K is None,
        "calib": str(calib_path) if calib_path else None,
    }

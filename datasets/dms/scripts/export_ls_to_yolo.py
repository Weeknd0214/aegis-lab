#!/usr/bin/env python3
"""Label Studio ls_annotations JSON → YOLO detect / YOLO pose txt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DMS_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = DMS_ROOT / "configs"
REGISTRY_PATH = DMS_ROOT / "datasets.registry.yaml"
KPT_ORDER_DIR = CONFIG_DIR / "keypoint_order"

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"}
ANNOTATIONS_DIRNAME = "ls_annotations"


def _load_registry() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


def _resolve_task_config(task: str, mode: str | None = None) -> dict[str, Any]:
    from task_registry import get_mode_config, resolve_task_id

    reg = _load_registry()
    task_r, mode_r = resolve_task_id(task, mode)
    return get_mode_config(task_r, mode_r, reg)


def _class_name_to_id(names: list[str] | dict[int | str, str]) -> dict[str, int]:
    if isinstance(names, dict):
        return {str(v): int(k) for k, v in names.items()}
    return {name: idx for idx, name in enumerate(names)}


def _load_kpt_label_map(task: str) -> dict[str, int]:
    path = KPT_ORDER_DIR / f"{task}_37.yaml"
    if not path.is_file():
        path = KPT_ORDER_DIR / f"{task}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"keypoint manifest not found for task {task}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for item in data.get("keypoints") or []:
        out[str(item["label"])] = int(item["id"])
    return out


def _task_id_for_image(image_path: Path, batch_dir: Path) -> str:
    try:
        rel = image_path.relative_to(batch_dir)
        stem = rel.as_posix()
    except ValueError:
        stem = image_path.stem
    return hashlib.sha256(stem.encode()).hexdigest()[:16]


def _iter_batch_images(batch_dir: Path) -> list[Path]:
    if not batch_dir.is_dir():
        return []
    candidates: list[Path] = []
    search_roots = [
        batch_dir / "images",
        batch_dir / "images" / "train",
        batch_dir,
    ]
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


def _label_out_path(image_path: Path, batch_dir: Path) -> Path:
    try:
        rel = image_path.relative_to(batch_dir)
    except ValueError:
        rel = Path(image_path.name)
    parts = list(rel.parts)
    if parts and parts[0] == "images":
        parts = parts[1:]
    if parts and parts[0] in ("train", "val", "test"):
        split = parts[0]
        name = Path(*parts[1:]).with_suffix(".txt")
        return batch_dir / "labels" / split / name
    name = Path(*parts).with_suffix(".txt")
    return batch_dir / "labels" / name


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


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _ls_rect_to_yolo_bbox(value: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(value["x"])
    y = float(value["y"])
    w = float(value["width"])
    h = float(value["height"])
    cx = _clamp01((x + w / 2.0) / 100.0)
    cy = _clamp01((y + h / 2.0) / 100.0)
    nw = _clamp01(w / 100.0)
    nh = _clamp01(h / 100.0)
    return cx, cy, nw, nh


def _ls_point_to_yolo_xy(value: dict[str, Any]) -> tuple[float, float]:
    return _clamp01(float(value["x"]) / 100.0), _clamp01(float(value["y"]) / 100.0)


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    cx, cy, _, _ = bbox
    return cx, cy


def _parse_rectangles(
    regions: list[dict[str, Any]],
    class_map: dict[str, int],
) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    for region in regions:
        if region.get("type") != "rectanglelabels":
            continue
        value = region.get("value") or {}
        labels = value.get("rectanglelabels") or []
        if not labels:
            continue
        label = str(labels[0])
        if label not in class_map:
            continue
        bbox = _ls_rect_to_yolo_bbox(value)
        boxes.append({"class_id": class_map[label], "bbox": bbox, "region_id": region.get("id")})
    return boxes


def _parse_keypoints(
    regions: list[dict[str, Any]],
    kpt_map: dict[str, int],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for region in regions:
        rtype = region.get("type")
        if rtype not in ("keypointlabels", "keypoint"):
            continue
        value = region.get("value") or {}
        labels = value.get("keypointlabels") or []
        if not labels:
            continue
        label = str(labels[0])
        if label not in kpt_map:
            continue
        x, y = _ls_point_to_yolo_xy(value)
        points.append({"index": kpt_map[label], "x": x, "y": y, "region_id": region.get("id")})
    return points


def _assign_keypoints_to_boxes(
    boxes: list[dict[str, Any]],
    points: list[dict[str, Any]],
) -> dict[int | None, list[dict[str, Any]]]:
    if not boxes:
        return {None: points}
    if len(boxes) == 1:
        return {0: points}

    assigned: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(boxes))}
    for pt in points:
        best_i = 0
        best_d = float("inf")
        for i, box in enumerate(boxes):
            cx, cy = _bbox_center(box["bbox"])
            d = (pt["x"] - cx) ** 2 + (pt["y"] - cy) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        assigned[best_i].append(pt)
    return assigned


def _format_detect_line(class_id: int, bbox: tuple[float, float, float, float]) -> str:
    cx, cy, w, h = bbox
    return f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def _format_pose_line(
    class_id: int,
    bbox: tuple[float, float, float, float],
    points: list[dict[str, Any]],
    nk: int,
) -> str:
    slots: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * nk
    for pt in points:
        idx = int(pt["index"])
        if 0 <= idx < nk:
            slots[idx] = (pt["x"], pt["y"], 2.0)
    parts = _format_detect_line(class_id, bbox).split()
    for x, y, v in slots:
        parts.extend([f"{x:.6f}", f"{y:.6f}", f"{v:.6f}"])
    return " ".join(parts)


def convert_regions_to_yolo_lines(
    regions: list[dict[str, Any]],
    *,
    mode: str,
    class_map: dict[str, int],
    kpt_map: dict[str, int] | None = None,
    kpt_shape: list[int] | None = None,
) -> list[str]:
    if mode == "detect":
        lines = []
        for box in _parse_rectangles(regions, class_map):
            lines.append(_format_detect_line(box["class_id"], box["bbox"]))
        return lines

    if mode != "pose":
        raise ValueError(f"unsupported mode: {mode}")
    if not kpt_map or not kpt_shape:
        raise ValueError("pose mode requires kpt_map and kpt_shape")

    nk = int(kpt_shape[0])
    boxes = _parse_rectangles(regions, class_map)
    points = _parse_keypoints(regions, kpt_map)
    if not boxes:
        return []

    assigned = _assign_keypoints_to_boxes(boxes, points)
    lines: list[str] = []
    for i, box in enumerate(boxes):
        pts = assigned.get(i, [])
        lines.append(_format_pose_line(box["class_id"], box["bbox"], pts, nk))
    return lines


def export_batch(
    batch_dir: Path,
    task: str,
    *,
    mode: str,
    task_mode: str | None = None,
    out_subdir: str | None = None,
) -> dict[str, Any]:
    batch_dir = batch_dir.resolve()
    tcfg = _resolve_task_config(task, task_mode)
    class_map = _class_name_to_id(tcfg.get("names") or {})
    kpt_map: dict[str, int] | None = None
    kpt_shape: list[int] | None = None
    if mode == "pose":
        kpt_map = _load_kpt_label_map(task)
        kpt_shape = list(tcfg.get("kpt_shape") or [37, 3])

    ann_dir = batch_dir / "labels" / ANNOTATIONS_DIRNAME
    written = 0
    skipped_empty = 0
    missing_ann = 0

    for image_path in _iter_batch_images(batch_dir):
        task_id = _task_id_for_image(image_path, batch_dir)
        ann_path = ann_dir / f"{task_id}.json"
        if not ann_path.is_file():
            missing_ann += 1
            continue
        data = json.loads(ann_path.read_text(encoding="utf-8"))
        regions = _extract_result_regions(data)
        if not regions:
            skipped_empty += 1
            continue
        lines = convert_regions_to_yolo_lines(
            regions,
            mode=mode,
            class_map=class_map,
            kpt_map=kpt_map,
            kpt_shape=kpt_shape,
        )
        if not lines:
            skipped_empty += 1
            continue
        out_path = _label_out_path(image_path, batch_dir)
        if out_subdir:
            # 显式覆盖：相对 batch_dir 的子目录 + 文件名
            out_path = batch_dir / out_subdir / f"{image_path.stem}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1

    return {
        "ok": True,
        "batch_dir": str(batch_dir),
        "task": task,
        "mode": mode,
        "written": written,
        "skipped_empty": skipped_empty,
        "missing_ann": missing_ann,
        "out_subdir": out_subdir or "auto",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Label Studio annotations to YOLO txt")
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--mode", choices=("detect", "pose"), required=True)
    parser.add_argument("--task-mode", default=None, help="dam batch_0516 / batch_0417 等")
    parser.add_argument("--out-subdir", default="labels/train")
    args = parser.parse_args(argv)

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))

    result = export_batch(
        args.batch_dir,
        args.task,
        mode=args.mode,
        task_mode=args.task_mode,
        out_subdir=args.out_subdir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["written"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

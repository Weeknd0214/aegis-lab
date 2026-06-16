"""标注格式转换器：KITTI / CVAT JSON / YOLO / COCO / HSAP quaternion 互转。"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════
# Quaternion ↔ Euler 辅助
# ═══════════════════════════════════════════════════════

def quat_to_rot_y(qw: float, qx: float, qy: float, qz: float) -> float:
    """四元数 → 绕 Y 轴旋转角 (KITTI rot_y)。"""
    # rot_y = atan2(2*(qw*qy + qx*qz), 1 - 2*(qy^2 + qx^2))
    sin_y = 2.0 * (qw * qy + qx * qz)
    cos_y = 1.0 - 2.0 * (qy * qy + qx * qx)
    return math.atan2(sin_y, cos_y)


def rot_y_to_quat(rot_y: float) -> tuple[float, float, float, float]:
    """绕 Y 轴旋转角 → 四元数 (qw, qx, qy, qz)。"""
    half = rot_y / 2.0
    return (math.cos(half), 0.0, math.sin(half), 0.0)


# ═══════════════════════════════════════════════════════
# 原始 quaternion 格式 → KITTI label_2
# ═══════════════════════════════════════════════════════

def quaternion_line_to_kitti(line: str, calib_bbox_fn=None) -> str | None:
    """将一行 quaternion 格式转为 KITTI label_2 行。

    输入格式 (空格分隔):
        Class x y z w l h qw qx qy qz class_id truncation [bbox_2d_8values] [extra...]

    输出格式 (KITTI label_2):
        Class truncated occluded alpha bbox_x1 bbox_y1 bbox_x2 bbox_y2 h w l x y z rot_y [score]
    """
    parts = line.strip().split()
    if len(parts) < 13:
        return None

    label = parts[0]
    x = float(parts[1])
    y = float(parts[2])
    z = float(parts[3])
    w = float(parts[4])
    l = float(parts[5])
    h_dim = float(parts[6])
    qw = float(parts[7])
    qx = float(parts[8])
    qy = float(parts[9])
    qz = float(parts[10])
    class_id = int(parts[11]) if len(parts) > 11 else 0
    truncation = int(parts[12]) if len(parts) > 12 else 0

    rot_y = quat_to_rot_y(qw, qx, qy, qz)
    # KITTI: alpha = rot_y - arctan(center_x / center_z), 简化处理
    alpha = rot_y

    # 2D bbox (如果存在: 后续8个值)
    bbox_2d = None
    if len(parts) >= 21:
        try:
            bbox_2d = [float(p) for p in parts[13:21]]
        except ValueError:
            pass

    # 截断和遮挡
    occluded = 0  # quaternion 格式没有直接对应

    # KITTI 位置是 camera coordinate: x(right), y(down), z(forward)
    # quaternion 格式是 LiDAR coordinate: x(forward), y(left), z(up)
    # 简化转换：x_kitti = -y_lidar, y_kitti = -z_lidar, z_kitti = x_lidar
    kitti_x = -y
    kitti_y = -z
    kitti_z = x

    # KITTI 3D 尺寸: height, width, length
    if bbox_2d and len(bbox_2d) == 8:
        x1, y1, x2, y2 = bbox_2d[0:4]
    else:
        x1 = y1 = x2 = y2 = 0

    # Format: Class truncated occluded alpha x1 y1 x2 y2 h w l x y z rot_y
    return (
        f"{label} {truncation} {occluded} {alpha:.6f} "
        f"{x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f} "
        f"{h_dim:.6f} {w:.6f} {l:.6f} "
        f"{kitti_x:.6f} {kitti_y:.6f} {kitti_z:.6f} "
        f"{rot_y:.6f}"
    )


# ═══════════════════════════════════════════════════════
# KITTI → 原始 quaternion 格式
# ═══════════════════════════════════════════════════════

def kitti_line_to_quaternion(line: str) -> str | None:
    """KITTI label_2 → quaternion 格式（回传HSAP）。"""
    parts = line.strip().split()
    if len(parts) < 15:
        return None

    label = parts[0]
    alpha = float(parts[3])
    bbox = [float(p) for p in parts[4:8]]
    h_dim = float(parts[8])
    w = float(parts[9])
    l = float(parts[10])
    kx = float(parts[11])
    ky = float(parts[12])
    kz = float(parts[13])
    rot_y = float(parts[14])

    # 逆转换
    x = kz  # LiDAR X = KITTI Z
    y = -kx  # LiDAR Y = -KITTI X
    z = -ky  # LiDAR Z = -KITTI Y

    qw, qx, qy, qz = rot_y_to_quat(rot_y)

    # 输出 quaternion 格式
    return (
        f"{label} {x:.6f} {y:.6f} {z:.6f} {w:.6f} {l:.6f} {h_dim:.6f} "
        f"{qw:.6f} {qx:.6f} {qy:.6f} {qz:.6f} 0 0 "
        f"{bbox[0]:.2f} {bbox[1]:.2f} {bbox[2]:.2f} {bbox[3]:.2f} "
        f"0 0 0 0 0 0 1"
    )


# ═══════════════════════════════════════════════════════
# CVAT Job API shapes → HSAP / YOLO
# ═══════════════════════════════════════════════════════

def cvat_shape_to_result_item(
    shape: dict[str, Any],
    label_map: dict[int, str],
) -> dict[str, Any]:
    """CVAT Job annotations API 单条 shape → HSAP result 条目。"""
    label = label_map.get(shape.get("label_id"), "unknown")
    stype = shape.get("type", "")
    item: dict[str, Any] = {
        "type": stype,
        "label": label,
        "source": "cvat",
        "cvat_id": shape.get("id"),
        "frame": shape.get("frame", 0),
    }
    if stype == "rectangle":
        item["points"] = [
            shape.get("xtl", 0),
            shape.get("ytl", 0),
            shape.get("xbr", 0),
            shape.get("ybr", 0),
        ]
    elif stype == "cuboid":
        for key in (
            "xtl1", "ytl1", "xtr1", "ytr1", "xbl1", "ybl1", "xbr1", "ybr1",
            "xtl2", "ytl2", "xtr2", "ytr2", "xbl2", "ybl2", "xbr2", "ybr2",
        ):
            if key in shape:
                item[key] = shape[key]
        if shape.get("points"):
            item["points"] = shape["points"]
    elif stype in ("polyline", "polygon", "points"):
        item["points"] = shape.get("points", [])
    return item


def cvat_job_shapes_to_yolo_lines(
    shapes: list[dict[str, Any]],
    label_map: dict[int, str],
    class_map: dict[str, int],
    img_width: int,
    img_height: int,
) -> list[str]:
    lines: list[str] = []
    for shape in shapes:
        if shape.get("type") != "rectangle":
            continue
        label = label_map.get(shape.get("label_id"), "")
        class_id = class_map.get(label)
        if class_id is None:
            # 尝试大小写不敏感匹配
            for name, cid in class_map.items():
                if name.lower() == label.lower():
                    class_id = cid
                    break
        if class_id is None:
            continue
        x1, y1, x2, y2 = (
            float(shape.get("xtl", 0)),
            float(shape.get("ytl", 0)),
            float(shape.get("xbr", 0)),
            float(shape.get("ybr", 0)),
        )
        if img_width <= 0 or img_height <= 0:
            continue
        cx = ((x1 + x2) / 2) / img_width
        cy = ((y1 + y2) / 2) / img_height
        bw = (x2 - x1) / img_width
        bh = (y2 - y1) / img_height
        lines.append(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return lines


def group_cvat_job_shapes_by_frame(
    job_annotations: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for shape in job_annotations.get("shapes") or []:
        frame = int(shape.get("frame", 0))
        grouped.setdefault(frame, []).append(shape)
    return grouped


def cvat_shapes_to_export_regions(
    shapes: list[dict[str, Any]],
    label_map: dict[int, str],
    img_width: int,
    img_height: int,
) -> list[dict[str, Any]]:
    """CVAT Job shapes → HSAP 导出链兼容的 result[]（原 Label Studio 字段布局）。"""
    if img_width <= 0 or img_height <= 0:
        return []

    regions: list[dict[str, Any]] = []
    for shape in shapes:
        stype = shape.get("type") or ""
        label = label_map.get(shape.get("label_id"), "unknown")
        base = {
            "id": str(shape.get("id", "")),
            "original_width": img_width,
            "original_height": img_height,
        }

        if stype == "rectangle":
            xtl = float(shape.get("xtl", 0))
            ytl = float(shape.get("ytl", 0))
            xbr = float(shape.get("xbr", 0))
            ybr = float(shape.get("ybr", 0))
            regions.append({
                **base,
                "type": "rectanglelabels",
                "value": {
                    "x": xtl / img_width * 100.0,
                    "y": ytl / img_height * 100.0,
                    "width": (xbr - xtl) / img_width * 100.0,
                    "height": (ybr - ytl) / img_height * 100.0,
                    "rotation": 0,
                    "rectanglelabels": [label],
                },
            })
        elif stype == "points":
            pts = shape.get("points") or []
            if len(pts) < 2:
                continue
            regions.append({
                **base,
                "type": "keypointlabels",
                "value": {
                    "x": float(pts[0]) / img_width * 100.0,
                    "y": float(pts[1]) / img_height * 100.0,
                    "width": 0.5,
                    "keypointlabels": [label],
                },
            })
        elif stype in ("polyline", "polygon"):
            regions.append({
                **base,
                "type": "polyline",
                "label": label,
                "points": list(shape.get("points") or []),
            })
        elif stype == "cuboid":
            item = cvat_shape_to_result_item(shape, label_map)
            item["original_width"] = img_width
            item["original_height"] = img_height
            regions.append(item)
    return regions


# ═══════════════════════════════════════════════════════
# CVAT JSON → YOLO bbox
# ═══════════════════════════════════════════════════════

def cvat_json_to_yolo(
    cvat_annotations: dict[str, Any],
    class_map: dict[str, int],
    img_width: int = 1920,
    img_height: int = 1080,
) -> dict[str, list[str]]:
    """CVAT annotations JSON → YOLO 格式文件内容。

    返回 {image_name: [yolo_line, ...]} 的字典。
    """
    result: dict[str, list[str]] = {}

    for img_ann in cvat_annotations.get("annotations", []):
        frame = img_ann.get("frame", 0)
        img_name = _resolve_image_name(cvat_annotations, img_ann)
        lines: list[str] = []

        for shape in img_ann.get("shapes", []):
            shape_type = shape.get("type", "")
            label_name = shape.get("label", "")
            class_id = class_map.get(label_name)
            if class_id is None:
                continue

            if shape_type == "rectangle":
                # YOLO: class_id cx cy w h (归一化 0-1)
                x1, y1, x2, y2 = (shape.get(p, 0) for p in ("xtl", "ytl", "xbr", "ybr"))
                cx = ((x1 + x2) / 2) / img_width
                cy = ((y1 + y2) / 2) / img_height
                bw = (x2 - x1) / img_width
                bh = (y2 - y1) / img_height
                lines.append(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        if lines:
            result[img_name] = lines

    return result


# ═══════════════════════════════════════════════════════
# CVAT JSON → COCO keypoints
# ═══════════════════════════════════════════════════════

def cvat_json_to_coco_keypoints(
    cvat_annotations: dict[str, Any],
    keypoint_labels: list[str],
    image_dir: Path | None = None,
) -> dict[str, Any]:
    """提取 CVAT 关键点标注 → COCO keypoints 格式。"""
    images: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    # 构建 keypoint_label → id 映射
    kp_map = {name: i for i, name in enumerate(keypoint_labels)}

    ann_id = 0
    for img_idx, img_ann in enumerate(cvat_annotations.get("annotations", [])):
        img_name = _resolve_image_name(cvat_annotations, img_ann)
        img_w = img_ann.get("width", 1920)
        img_h = img_ann.get("height", 1080)
        img_id = img_idx + 1
        images.append({"id": img_id, "file_name": img_name, "width": img_w, "height": img_h})

        for shape in img_ann.get("shapes", []):
            if shape.get("type") != "points":
                continue
            points = shape.get("points", [])
            if not points:
                continue
            # points 格式: [[x1,y1], [x2,y2], ...]
            keypoints_list: list[float] = []
            num_keypoints = 0
            for kp_label in keypoint_labels:
                kp_data = next((p for p in points if p.get("label") == kp_label), None)
                if kp_data:
                    keypoints_list.extend([kp_data.get("x", 0), kp_data.get("y", 0), 2])  # visible
                    num_keypoints += 1
                else:
                    keypoints_list.extend([0, 0, 0])  # not labeled

            annotations.append({
                "id": ann_id,
                "image_id": img_id,
                "category_id": 1,
                "keypoints": keypoints_list,
                "num_keypoints": num_keypoints,
                "bbox": _keypoint_bbox(keypoints_list, img_w, img_h),
            })
            ann_id += 1

    return {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 1, "name": "person", "keypoints": keypoint_labels, "skeleton": []}],
    }


# ═══════════════════════════════════════════════════════
# CVAT JSON → HSAP Lane polyline
# ═══════════════════════════════════════════════════════

def cvat_json_to_lane_polylines(
    cvat_annotations: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """提取 CVAT 折线标注 → HSAP 车道线格式。"""
    result: dict[str, list[dict[str, Any]]] = {}

    for img_ann in cvat_annotations.get("annotations", []):
        img_name = _resolve_image_name(cvat_annotations, img_ann)
        polylines: list[dict[str, Any]] = []

        for shape in img_ann.get("shapes", []):
            if shape.get("type") not in ("polyline", "polygon"):
                continue
            points = shape.get("points", [])
            if not points:
                continue
            attrs = {a.get("name"): a.get("value") for a in (shape.get("attributes") or [])}
            polylines.append({
                "label": shape.get("label", "lane_line"),
                "attributes": attrs,
                "points": [[p.get("x", 0), p.get("y", 0)] for p in points],
            })

        if polylines:
            result[img_name] = polylines

    return result


# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════

def _resolve_image_name(annotations: dict[str, Any], img_ann: dict[str, Any]) -> str:
    """从 CVAT annotation JSON 中解析图像文件名。"""
    frame = img_ann.get("frame", 0)
    images = annotations.get("images", [])
    if isinstance(images, list) and frame < len(images):
        img_info = images[frame]
        if isinstance(img_info, dict):
            return img_info.get("file_name", f"frame_{frame}")
    return img_ann.get("name", f"frame_{frame}")


def _keypoint_bbox(kpts: list[float], img_w: int, img_h: int) -> list[float]:
    """从 keypoints 列表计算 bbox [x, y, w, h]。"""
    xs = [kpts[i] for i in range(0, len(kpts), 3) if kpts[i + 2] > 0]
    ys = [kpts[i + 1] for i in range(0, len(kpts), 3) if kpts[i + 2] > 0]
    if not xs or not ys:
        return [0, 0, 0, 0]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return [x_min, y_min, x_max - x_min, y_max - y_min]


# ═══════════════════════════════════════════════════════
# 批量 KITTI 转换
# ═══════════════════════════════════════════════════════

def convert_quaternion_dir_to_kitti(label_dir: Path, output_dir: Path) -> int:
    """将 quaternion 格式目录批量转换为 KITTI label_2 格式。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for txt_file in sorted(label_dir.rglob("*.txt")):
        kitti_lines: list[str] = []
        for line in txt_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            kitti_line = quaternion_line_to_kitti(line)
            if kitti_line:
                kitti_lines.append(kitti_line)
        if kitti_lines:
            out_file = output_dir / txt_file.name
            out_file.write_text("\n".join(kitti_lines) + "\n", encoding="utf-8")
            count += 1
    return count


def convert_cvat_kitti_export_to_hsap(kitti_data: bytes, output_dir: Path) -> int:
    """将 CVAT KITTI 导出（zip 字节）解压并转为 HSAP quaternion 格式。"""
    import io
    import zipfile

    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(io.BytesIO(kitti_data)) as zf:
        for name in zf.namelist():
            if not name.endswith(".txt") or "label_2" not in name:
                continue
            content = zf.read(name).decode("utf-8")
            hsap_lines: list[str] = []
            for line in content.strip().split("\n"):
                if not line.strip():
                    continue
                hsap_line = kitti_line_to_quaternion(line)
                if hsap_line:
                    hsap_lines.append(hsap_line)
            if hsap_lines:
                fname = Path(name).name
                (output_dir / fname).write_text("\n".join(hsap_lines) + "\n", encoding="utf-8")
                count += 1
    return count


# ═══════════════════════════════════════════════════════
# CVAT cuboid 16pt → HSAP quaternion_json detection (MVP)
# ═══════════════════════════════════════════════════════

CUBOID_7CLS_NAMES = [
    "pedestrian",
    "car",
    "truck",
    "bus",
    "motorcycle",
    "tricycle",
    "traffic cone",
]


def cuboid_points_to_box2d(points: list[float]) -> list[float] | None:
    """从 CVAT cuboid 16 点（8 个 x,y 对）计算 axis-aligned 2D bbox。"""
    if len(points) < 16:
        return None
    xs = [float(points[i]) for i in range(0, 16, 2)]
    ys = [float(points[i]) for i in range(1, 16, 2)]
    return [min(xs), min(ys), max(xs), max(ys)]


def cuboid_item_to_detection(
    item: dict[str, Any],
    class_map: dict[str, int],
    *,
    K: list[list[float]] | None = None,
) -> dict[str, Any] | None:
    """ls_annotations cuboid 条目 → quaternion_json detection（MVP：2D bbox + 可选 3D 占位）。"""
    label = str(item.get("label") or "")
    class_id = class_map.get(label)
    if class_id is None:
        for name, cid in class_map.items():
            if name.lower() == label.lower():
                class_id = cid
                break
    if class_id is None:
        return None

    points = item.get("points") or []
    if len(points) < 16:
        for key in (
            "xtl1", "ytl1", "xtr1", "ytr1", "xbl1", "ybl1", "xbr1", "ybr1",
            "xtl2", "ytl2", "xtr2", "ytr2", "xbl2", "ybl2", "xbr2", "ybr2",
        ):
            if key in item:
                points.append(float(item[key]))
    box2d = cuboid_points_to_box2d(points)
    if not box2d:
        return None

    det: dict[str, Any] = {
        "class_id": class_id,
        "class_name": label,
        "score": 1.0,
        "box2d_xyxy": box2d,
        "fit_ok": False,
    }
    if K:
        det["K_used"] = True
    return det


# ═══════════════════════════════════════════════════════
# ADAS 3D Quaternion JSON → CVAT cuboid XML
# ═══════════════════════════════════════════════════════

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from datetime import datetime, timezone


def _get_np():
    """Lazy numpy import."""
    import numpy as np
    return np


def _quat_to_rotation_matrix(qw: float, qx: float, qy: float, qz: float):
    np = _get_np()
    return np.array([
        [1 - 2*qy**2 - 2*qz**2, 2*qx*qy - 2*qz*qw,     2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,     1 - 2*qx**2 - 2*qz**2,  2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,     2*qy*qz + 2*qx*qw,      1 - 2*qx**2 - 2*qy**2],
    ])


def _get_3d_corners(center, w, l, h, qw, qx, qy, qz):
    """Compute 8 corners in camera coordinates.
    Object frame: x=forward(±l/2), y=left(±w/2), z=up(±h/2)."""
    np = _get_np()
    ox = np.array([-l/2, -l/2, -l/2, -l/2,  l/2,  l/2,  l/2,  l/2])
    oy = np.array([-w/2,  w/2,  w/2, -w/2, -w/2,  w/2,  w/2, -w/2])
    oz = np.array([-h/2, -h/2,  h/2,  h/2, -h/2, -h/2,  h/2,  h/2])
    corners_obj = np.stack([ox, oy, oz], axis=1)
    R = _quat_to_rotation_matrix(qw, qx, qy, qz)
    return (R @ corners_obj.T).T + np.array(center)


def _project_2d(pts_3d, K):
    pts = pts_3d @ K.T
    return pts[:, :2] / pts[:, 2:]


def quaternion_json_to_cvat_cuboid_xml(
    json_dir: str | Path,
    image_names: list[str],
    task_id: int | None = None,
) -> str:
    """将 ADAS 3D quaternion JSON 标注转换为 CVAT cuboid XML。

    Args:
        json_dir: 包含 .json 标注文件的目录
        image_names: 图像文件名列表（与 CVAT task 中的 frame 顺序对应）
        task_id: 可选 CVAT task ID

    Returns:
        CVAT for images 1.1 XML 字符串
    """
    json_dir = Path(json_dir)
    root = Element("annotations")
    SubElement(root, "version").text = "1.1"
    meta = SubElement(root, "meta")
    te = SubElement(meta, "task")
    SubElement(te, "id").text = str(task_id or 0)
    SubElement(te, "name").text = "ADAS 3D"
    SubElement(te, "size").text = str(len(image_names))
    SubElement(te, "mode").text = "annotation"
    SubElement(te, "overlap").text = "0"
    now = datetime.now(timezone.utc).isoformat()
    SubElement(te, "created").text = now
    SubElement(te, "updated").text = now
    le = SubElement(te, "labels")
    for lbl in ["car", "pedestrian", "truck", "bus", "motorcycle", "tricycle", "traffic cone"]:
        l = SubElement(le, "label"); SubElement(l, "name").text = lbl; SubElement(l, "attributes")
    se = SubElement(te, "segments"); s = SubElement(se, "segment")
    SubElement(s, "id").text = "1"; SubElement(s, "start").text = "0"
    SubElement(s, "stop").text = str(len(image_names) - 1)
    ow = SubElement(te, "owner"); SubElement(ow, "username").text = "platform"; SubElement(ow, "email").text = ""
    SubElement(meta, "dumped").text = now

    total = 0
    for fid, img_name in enumerate(image_names):
        stem = Path(img_name).stem
        jp = json_dir / f"{stem}.json"
        if not jp.is_file():
            continue

        ann = json.loads(jp.read_text(encoding="utf-8"))
        np = _get_np()
        K = np.array(ann["K"])
        img_w, img_h = ann["image_size"]

        ie = SubElement(root, "image")
        ie.set("id", str(fid))
        ie.set("name", Path(img_name).name)
        ie.set("width", str(img_w))
        ie.set("height", str(img_h))

        for det in ann.get("detections", []):
            w, l, h = det["dimensions_wlh"]
            c3d = _get_3d_corners(det["center_3d"], w, l, h, *det["quaternion_wxyz"])
            if _get_np().any(c3d[:, 2] <= 0):
                continue
            c2d = _project_2d(c3d, K)

            # 4 edge-pairs: (rear, front) × (tl, tr, bl, br)
            pairs = [(3, 7), (2, 6), (0, 4), (1, 5)]
            pd = []
            for ri, fi in pairs:
                mid = (c2d[ri] + c2d[fi]) / 2.0
                f1_i, f2_i = (fi, ri) if c3d[fi, 2] <= c3d[ri, 2] else (ri, fi)
                pd.append({"mid": mid, "f1_i": f1_i, "f2_i": f2_i})

            pd.sort(key=lambda p: p["mid"][1])
            top = sorted(pd[:2], key=lambda p: p["mid"][0])
            bot = sorted(pd[2:], key=lambda p: p["mid"][0])
            tl, tr = top[0], top[1]
            bl, br = bot[0], bot[1]

            cub = SubElement(ie, "cuboid")
            cub.set("label", det["class_name"]); cub.set("source", "manual"); cub.set("occluded", "0")
            cub.set("xtl1", f"{c2d[tl['f1_i']][0]:.2f}"); cub.set("ytl1", f"{c2d[tl['f1_i']][1]:.2f}")
            cub.set("xtr1", f"{c2d[tr['f1_i']][0]:.2f}"); cub.set("ytr1", f"{c2d[tr['f1_i']][1]:.2f}")
            cub.set("xbl1", f"{c2d[bl['f1_i']][0]:.2f}"); cub.set("ybl1", f"{c2d[bl['f1_i']][1]:.2f}")
            cub.set("xbr1", f"{c2d[br['f1_i']][0]:.2f}"); cub.set("ybr1", f"{c2d[br['f1_i']][1]:.2f}")
            cub.set("xtl2", f"{c2d[tl['f2_i']][0]:.2f}"); cub.set("ytl2", f"{c2d[tl['f2_i']][1]:.2f}")
            cub.set("xtr2", f"{c2d[tr['f2_i']][0]:.2f}"); cub.set("ytr2", f"{c2d[tr['f2_i']][1]:.2f}")
            cub.set("xbl2", f"{c2d[bl['f2_i']][0]:.2f}"); cub.set("ybl2", f"{c2d[bl['f2_i']][1]:.2f}")
            cub.set("xbr2", f"{c2d[br['f2_i']][0]:.2f}"); cub.set("ybr2", f"{c2d[br['f2_i']][1]:.2f}")
            cub.set("z_order", "0")
            total += 1

    xml_str = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    return xml_str

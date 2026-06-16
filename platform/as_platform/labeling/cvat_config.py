"""CVAT 标注配置：为 DMS / ADAS / Lane 生成 label schema（唯一标注引擎）。"""
from __future__ import annotations

from typing import Any

from as_platform.config import WORKSPACE
from as_platform.labeling.scope import labeling_profile_key, load_dms_registry, load_labeling_registry

# Lane 车道线 — 折线
LANE_LABELS: list[dict[str, Any]] = [
    {
        "name": "lane_line",
        "type": "polyline",
        "attributes": [
            {
                "name": "type",
                "mutable": False,
                "input_type": "select",
                "values": ["solid", "dashed", "double_solid", "double_dashed", "solid_dashed"],
                "default_value": "solid",
            },
            {
                "name": "color",
                "mutable": False,
                "input_type": "select",
                "values": ["white", "yellow", "blue", "other"],
                "default_value": "white",
            },
        ],
    },
    {
        "name": "curb",
        "type": "polyline",
        "attributes": [
            {
                "name": "type",
                "mutable": False,
                "input_type": "select",
                "values": ["high", "low", "none"],
                "default_value": "low",
            },
        ],
    },
    {"name": "stop_line", "type": "polyline"},
]

# ADAS cuboid_7cls — 单目图像 cuboid
ADAS_CUBOID_7CLS_LABELS: list[dict[str, Any]] = [
    {"name": "car", "type": "cuboid"},
    {"name": "pedestrian", "type": "cuboid"},
    {"name": "truck", "type": "cuboid"},
    {"name": "bus", "type": "cuboid"},
    {"name": "motorcycle", "type": "cuboid"},
    {"name": "tricycle", "type": "cuboid"},
    {"name": "traffic cone", "type": "cuboid"},
]


def _rect_label(name: str, **attrs: Any) -> dict[str, Any]:
    lb: dict[str, Any] = {"name": name, "type": "rectangle"}
    if attrs:
        lb["attributes"] = attrs
    return lb


def _dms_registry_task_config(task: str, mode: str | None) -> dict[str, Any]:
    import sys

    scripts = WORKSPACE / "datasets" / "dms" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from task_registry import get_mode_config, resolve_task_id

    reg = load_dms_registry()
    task_r, mode_r = resolve_task_id(task, mode)
    return get_mode_config(task_r, mode_r, reg)


def _labels_from_class_names(names: list[str] | dict[int | str, str]) -> list[dict[str, Any]]:
    if isinstance(names, dict):
        ordered = [names[k] for k in sorted(names, key=lambda x: int(x))]
    else:
        ordered = list(names)
    return [_rect_label(str(n)) for n in ordered]


def _dms_pose_labels() -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = [_rect_label("face")]
    labels.extend({"name": f"kp_{i:02d}", "type": "points"} for i in range(37))
    return labels


def _dms_labels(task: str, mode: str | None) -> list[dict[str, Any]]:
    tcfg = _dms_registry_task_config(task, mode)
    ttype = tcfg.get("type") or "detect"
    if ttype == "pose":
        return _dms_pose_labels()
    names = tcfg.get("names")
    if names:
        return _labels_from_class_names(names)
    return [_rect_label("object")]


def _labels_from_registry_profile(project: str, task: str, mode: str | None) -> list[dict[str, Any]] | None:
    reg = load_dms_registry() if project == "dms" else None
    pk = labeling_profile_key(project, task, mode, reg)
    prof = (load_labeling_registry().get("profiles") or {}).get(pk) or {}
    cvat_names = prof.get("cvat_labels")
    if cvat_names:
        label_type = prof.get("cvat_label_type") or (
            "cuboid" if project == "adas" and task == "cuboid_7cls" else "rectangle"
        )
        return [{"name": str(n), "type": label_type} for n in cvat_names]
    return None


def build_cvat_labels(
    project: str,
    task: str | None = None,
    mode: str | None = None,
    annotation_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """根据 HSAP project/task/mode 生成 CVAT Task 的 labels 定义。"""
    task = task or ""
    prof_labels = _labels_from_registry_profile(project, task, mode)
    if prof_labels is not None:
        return prof_labels

    if project == "adas":
        if task == "cuboid_7cls":
            return ADAS_CUBOID_7CLS_LABELS
        if task == "det_7cls":
            return [_rect_label(n) for n in [
                "pedestrian", "car", "truck", "bus", "motorcycle", "tricycle", "traffic cone",
            ]]
        return ADAS_CUBOID_7CLS_LABELS

    if project == "lane":
        return LANE_LABELS

    if project == "dms":
        return _dms_labels(task, mode)

    return [_rect_label("object")]


def resolve_annotation_types(project: str, task: str | None = None, mode: str | None = None) -> list[str]:
    mapping = {
        "dms": ["bbox", "keypoint"],
        "adas": ["cuboid"],
        "lane": ["polyline"],
    }
    if project == "adas" and task == "cuboid_7cls":
        return ["cuboid"]
    if project == "adas" and task == "det_7cls":
        return ["bbox"]
    if project == "dms" and task == "adas":
        return ["bbox"]
    return mapping.get(project, ["bbox"])

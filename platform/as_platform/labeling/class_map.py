"""ADAS class_id 映射（BK2/MOON 单源）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from as_platform.config import WORKSPACE

_ADAS_REGISTRY = WORKSPACE / "datasets" / "adas" / "adas.registry.yaml"
_LABELING_REGISTRY = WORKSPACE / "datasets" / "labeling.registry.yaml"


def load_adas_class_names() -> list[str]:
    if _ADAS_REGISTRY.is_file():
        reg = yaml.safe_load(_ADAS_REGISTRY.read_text(encoding="utf-8")) or {}
        names = (reg.get("classes") or {}).get("names")
        if names:
            return [str(n) for n in names]
    if _LABELING_REGISTRY.is_file():
        reg = yaml.safe_load(_LABELING_REGISTRY.read_text(encoding="utf-8")) or {}
        labels = (reg.get("profiles") or {}).get("cuboid_7cls", {}).get("cvat_labels")
        if labels:
            return [str(n) for n in labels]
    from as_platform.labeling.format_converter import CUBOID_7CLS_NAMES

    return list(CUBOID_7CLS_NAMES)


def class_name_to_id(name: str, class_map: dict[str, int] | None = None) -> int | None:
    cmap = class_map or {n: i for i, n in enumerate(load_adas_class_names())}
    if name in cmap:
        return cmap[name]
    low = name.lower()
    for k, v in cmap.items():
        if k.lower() == low:
            return v
    return None


def build_class_map(names: list[str] | None = None) -> dict[str, int]:
    return {str(n): idx for idx, n in enumerate(names or load_adas_class_names())}


def remap_class_id(old_names: list[str], new_names: list[str], class_id: int) -> int:
    if class_id < 0 or class_id >= len(old_names):
        return class_id
    label = old_names[class_id]
    new_id = build_class_map(new_names).get(label)
    if new_id is None:
        for k, v in build_class_map(new_names).items():
            if k.lower() == label.lower():
                return v
    return new_id if new_id is not None else class_id


def normalize_detection_class(det: dict[str, Any], class_map: dict[str, int] | None = None) -> dict[str, Any]:
    cmap = class_map or build_class_map()
    name = str(det.get("class_name") or "")
    cid = det.get("class_id")
    if name:
        mapped = class_name_to_id(name, cmap)
        if mapped is not None:
            det = dict(det)
            det["class_id"] = mapped
            det["class_name"] = name
    elif cid is not None:
        names = list(cmap.keys())
        idx = int(cid)
        if 0 <= idx < len(names):
            det = dict(det)
            det["class_name"] = names[idx]
    return det

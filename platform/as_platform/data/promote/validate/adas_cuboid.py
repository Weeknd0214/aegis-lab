"""ADAS cuboid batch validation before promote."""
from __future__ import annotations

import json
from pathlib import Path

from as_platform.labeling.class_map import load_adas_class_names


def validate_adas_cuboid_batch(
    batch_dir: Path,
    *,
    allow_partial_3d: bool = False,
    min_fit_ratio: float = 0.8,
) -> tuple[list[str], list[str], dict]:
    """Return (errors, warnings, stats)."""
    errors: list[str] = []
    warnings: list[str] = []
    qdir = batch_dir / "labels" / "quaternion_json"
    expected_names = load_adas_class_names()

    if not qdir.is_dir():
        errors.append(f"missing labels/quaternion_json under {batch_dir}")
        return errors, warnings, {}

    files = sorted(qdir.glob("*.json"))
    if not files:
        errors.append("no quaternion_json files")
        return errors, warnings, {}

    total_dets = 0
    fit_ok = 0
    has_k = 0
    files_with_dets = 0
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{p.name}: invalid json ({e})")
            continue
        dets = data.get("detections") or []
        if not dets:
            warnings.append(f"{p.name}: empty detections (skipped)")
            continue
        files_with_dets += 1
        if data.get("K"):
            has_k += 1
        prompts = data.get("text_prompts") or []
        if prompts and list(prompts) != expected_names:
            warnings.append(f"{p.name}: text_prompts order differs from registry")
        for det in dets:
            total_dets += 1
            cid = det.get("class_id")
            if cid is None or int(cid) < 0 or int(cid) >= len(expected_names):
                errors.append(f"{p.name}: invalid class_id {cid}")
            if det.get("fit_ok"):
                fit_ok += 1

    stats = {
        "quaternion_files": len(files),
        "files_with_detections": files_with_dets,
        "detections": total_dets,
        "fit_ok_ratio": fit_ok / max(total_dets, 1),
        "has_k_ratio": has_k / max(files_with_dets, 1),
    }

    if files_with_dets == 0:
        errors.append("no quaternion json with detections")

    calib_dir = batch_dir / "calib"
    if calib_dir.is_dir() and list(calib_dir.glob("*.yaml")):
        if files_with_dets > 0 and has_k < files_with_dets:
            errors.append(f"calib present but only {has_k}/{files_with_dets} annotated json have K")
        if not allow_partial_3d and total_dets > 0:
            ratio = fit_ok / total_dets
            if ratio < min_fit_ratio:
                errors.append(
                    f"fit_ok ratio {ratio:.2f} < {min_fit_ratio} (use allow_partial_3d for pilot)"
                )

    return errors, warnings, stats

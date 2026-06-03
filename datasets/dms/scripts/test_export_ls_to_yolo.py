#!/usr/bin/env python3
"""export_ls_to_yolo 单元测试（无 pytest 依赖）。"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from export_ls_to_yolo import (  # noqa: E402
    convert_regions_to_yolo_lines,
    export_batch,
)
from ingest_incremental import validate_detect_label, validate_pose_label  # noqa: E402


def _task_id(rel: str) -> str:
    return hashlib.sha256(rel.encode()).hexdigest()[:16]


def test_detect_conversion() -> None:
    regions = [
        {
            "type": "rectanglelabels",
            "value": {
                "x": 10.0,
                "y": 20.0,
                "width": 30.0,
                "height": 40.0,
                "rectanglelabels": ["face"],
            },
        }
    ]
    lines = convert_regions_to_yolo_lines(
        regions,
        mode="detect",
        class_map={"face": 0, "eye_open": 1},
    )
    assert len(lines) == 1
    parts = lines[0].split()
    assert len(parts) == 5
    assert parts[0] == "0"
    assert abs(float(parts[1]) - 0.25) < 1e-5  # cx = (10+15)/100
    assert abs(float(parts[2]) - 0.40) < 1e-5  # cy = (20+20)/100
    err = validate_detect_label("\n".join(lines), 4)
    assert err is None, err


def test_pose_conversion() -> None:
    regions = [
        {
            "type": "rectanglelabels",
            "value": {
                "x": 10.0,
                "y": 20.0,
                "width": 30.0,
                "height": 40.0,
                "rectanglelabels": ["face"],
            },
        },
        {
            "type": "keypointlabels",
            "value": {"x": 35.6, "y": 52.9, "width": 0.5, "keypointlabels": ["kp_01"]},
        },
        {
            "type": "keypointlabels",
            "value": {"x": 50.0, "y": 50.0, "width": 0.5, "keypointlabels": ["kp_10"]},
        },
    ]
    kpt_map = {f"kp_{i:02d}": i for i in range(37)}
    lines = convert_regions_to_yolo_lines(
        regions,
        mode="pose",
        class_map={"face": 0},
        kpt_map=kpt_map,
        kpt_shape=[37, 3],
    )
    assert len(lines) == 1
    parts = lines[0].split()
    assert len(parts) == 116
    assert parts[0] == "0"
    # kp_01 at index 1 -> fields 5+3..5+5
    assert abs(float(parts[8]) - 0.356) < 1e-3
    assert abs(float(parts[9]) - 0.529) < 1e-3
    assert parts[10] == "2.000000"
    err = validate_pose_label("\n".join(lines), [37, 3])
    assert err is None, err


def test_export_batch_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        batch = Path(tmp)
        img_rel = "images/train/sample.jpg"
        img_path = batch / img_rel
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\xff\xd8\xff")

        tid = _task_id(img_rel)
        ann = {
            "task_id": tid,
            "result": [
                {
                    "type": "rectanglelabels",
                    "value": {
                        "x": 10.0,
                        "y": 20.0,
                        "width": 30.0,
                        "height": 40.0,
                        "rectanglelabels": ["face"],
                    },
                },
                {
                    "type": "keypointlabels",
                    "value": {"x": 25.0, "y": 40.0, "width": 0.5, "keypointlabels": ["kp_00"]},
                },
            ],
        }
        ann_dir = batch / "labels" / "ls_annotations"
        ann_dir.mkdir(parents=True)
        (ann_dir / f"{tid}.json").write_text(json.dumps(ann), encoding="utf-8")

        result = export_batch(batch, "addw_face", mode="pose")
        assert result["written"] == 1
        out = batch / "labels" / "train" / "sample.txt"
        assert out.is_file()
        parts = out.read_text().strip().split()
        assert len(parts) == 116


def main() -> int:
    test_detect_conversion()
    test_pose_conversion()
    test_export_batch_end_to_end()
    print("OK export_ls_to_yolo tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

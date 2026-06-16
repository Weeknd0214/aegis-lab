#!/usr/bin/env python3
"""Unified Ingest SDK 单元测试（无 pytest 依赖）。"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_stage_aliases() -> None:
    from as_platform.labeling.stage import effective_stage, matches_stage_filter

    assert effective_stage("review_approved") == "labeling_submitted"
    assert effective_stage("returned") == "returned"
    assert matches_stage_filter("review_approved", "labeling_submitted")
    assert not matches_stage_filter("raw_pool", "returned")


def test_bk2_class_map() -> None:
    from as_platform.labeling.class_map import (
        build_class_map,
        load_adas_class_names,
        normalize_detection_class,
        remap_class_id,
    )

    names = load_adas_class_names()
    assert names[0] == "pedestrian"
    assert names[1] == "car"
    cmap = build_class_map(names)
    assert cmap["car"] == 1
    assert cmap["pedestrian"] == 0

    old = ["car", "pedestrian", "truck", "bus", "motorcycle", "tricycle", "traffic cone"]
    assert remap_class_id(old, names, 0) == 1  # car was 0, now 1

    det = normalize_detection_class({"class_name": "car", "class_id": 99})
    assert det["class_id"] == 1


def test_validate_adas_cuboid() -> None:
    from as_platform.data.promote.validate.adas_cuboid import validate_adas_cuboid_batch
    from as_platform.labeling.class_map import load_adas_class_names

    with tempfile.TemporaryDirectory() as td:
        batch = Path(td)
        qdir = batch / "labels" / "quaternion_json"
        qdir.mkdir(parents=True)
        names = load_adas_class_names()
        good = {
            "detections": [{"class_id": 1, "class_name": "car", "fit_ok": False}],
            "text_prompts": names,
            "K": [[1000, 0, 960], [0, 1000, 540], [0, 0, 1]],
        }
        (qdir / "a.json").write_text(json.dumps(good), encoding="utf-8")
        (qdir / "empty.json").write_text(json.dumps({"detections": []}), encoding="utf-8")
        (batch / "calib").mkdir()
        (batch / "calib" / "cam.yaml").write_text("K: []\n", encoding="utf-8")

        errors, warnings, stats = validate_adas_cuboid_batch(batch, allow_partial_3d=True)
        assert not errors, errors
        assert stats["files_with_detections"] == 1
        assert any("empty" in w for w in warnings)


def test_fit_cuboid_detection() -> None:
    from algorithms.adas_mono3d.fit_cuboid import cuboid_points_to_box2d, fit_cuboid_detection

    pts = [770.0, 347.0, 834.0, 347.0, 772.0, 423.0, 835.0, 423.0,
           806.0, 357.0, 861.0, 357.0, 807.0, 422.0, 862.0, 422.0]
    box = cuboid_points_to_box2d(pts)
    assert box is not None
    assert box[0] < box[2] and box[1] < box[3]

    K = [[1189.7, 0, 1007.5], [0, 1189.7, 517.5], [0, 0, 1]]
    out = fit_cuboid_detection(pts, K, "car")
    assert "center_3d" in out
    assert "dimensions_wlh" in out
    assert "quaternion_wxyz" in out
    assert len(out["quaternion_wxyz"]) == 4


def test_export_cuboid_batch_class_id() -> None:
    from as_platform.labeling.export_cuboid_batch import export_batch

    with tempfile.TemporaryDirectory() as td:
        batch = Path(td)
        (batch / "images").mkdir()
        img = batch / "images" / "frame1.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        calib = batch / "calib" / "cam0.yaml"
        calib.parent.mkdir()
        calib.write_text(
            "K:\n  - [1000, 0, 960]\n  - [0, 1000, 540]\n  - [0, 0, 1]\n",
            encoding="utf-8",
        )
        ann_dir = batch / "labels" / "ls_annotations"
        ann_dir.mkdir(parents=True)
        ann = {
            "image": "frame1.jpg",
            "result": [{
                "type": "cuboid",
                "label": "car",
                "points": [770.0, 347.0, 834.0, 347.0, 772.0, 423.0, 835.0, 423.0,
                           806.0, 357.0, 861.0, 357.0, 807.0, 422.0, 862.0, 422.0],
                "original_width": 1920,
                "original_height": 1080,
            }],
        }
        import hashlib
        tid = hashlib.sha256(b"images/frame1.jpg").hexdigest()[:16]
        (ann_dir / f"{tid}.json").write_text(json.dumps(ann), encoding="utf-8")

        result = export_batch(batch)
        assert result["written"] == 1
        qjson = batch / "labels" / "quaternion_json" / "frame1.json"
        assert qjson.is_file()
        data = json.loads(qjson.read_text())
        assert data["text_prompts"][0] == "pedestrian"
        assert data["detections"][0]["class_id"] == 1
        assert data["detections"][0]["class_name"] == "car"


def test_refresh_adas_lists() -> None:
    from as_platform.data.promote.manifest import refresh_adas_lists

    with tempfile.TemporaryDirectory() as td:
        pack_root = Path(td) / "packs" / "test_pack"
        src = pack_root / "sources" / "batch_a" / "labels" / "quaternion_json"
        src.mkdir(parents=True)
        (src / "img1.json").write_text('{"detections":[{}]}', encoding="utf-8")
        (src / "img2.json").write_text('{"detections":[{}]}', encoding="utf-8")

        wf = {
            "projects": {
                "adas": {
                    "root": str(Path(td)),
                    "registry": "adas.registry.yaml",
                }
            }
        }
        (Path(td) / "adas.registry.yaml").write_text("split:\n  val_ratio: 0.5\n", encoding="utf-8")

        out = refresh_adas_lists(wf, pack="test_pack")
        train = Path(out["train_list"]).read_text().strip().splitlines()
        val = Path(out["val_list"]).read_text().strip().splitlines()
        assert len(train) + len(val) == 2
        assert Path(out["pack_index"]).is_file()


def test_promote_adas_dry_run() -> None:
    from as_platform.data.promote.adas_cuboid import AdasCuboidPromoteAdapter
    from as_platform.data.promote.base import PromoteContext
    from as_platform.labeling.class_map import load_adas_class_names

    with tempfile.TemporaryDirectory() as td:
        batch = Path(td) / "inbox" / "cuboid_7cls" / "b1"
        qdir = batch / "labels" / "quaternion_json"
        qdir.mkdir(parents=True)
        names = load_adas_class_names()
        payload = {
            "detections": [{"class_id": 1, "class_name": "car"}],
            "text_prompts": names,
            "K": [[1000, 0, 960], [0, 1000, 540], [0, 0, 1]],
        }
        (qdir / "f.json").write_text(json.dumps(payload), encoding="utf-8")
        (batch / "images").mkdir()
        (batch / "images" / "f.jpg").write_bytes(b"x")

        root = Path(td)
        ctx = PromoteContext(
            project="adas",
            task="cuboid_7cls",
            batch="b1",
            pack="test_pack",
            batch_dir=batch,
            project_root=root,
            dry_run=True,
        )
        adapter = AdasCuboidPromoteAdapter()
        assert adapter.validate(ctx) == []
        result = adapter.promote(ctx)
        assert result.ok
        assert result.detail.get("dry_run") is True


def main() -> None:
    tests = [
        test_stage_aliases,
        test_bk2_class_map,
        test_validate_adas_cuboid,
        test_fit_cuboid_detection,
        test_export_cuboid_batch_class_id,
        test_refresh_adas_lists,
        test_promote_adas_dry_run,
    ]
    for fn in tests:
        fn()
        print(f"OK {fn.__name__}")
    print(f"ALL {len(tests)} PASSED")


if __name__ == "__main__":
    main()

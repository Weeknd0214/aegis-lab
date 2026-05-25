"""数据整理：校验摘要写入 batch.meta。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from as_platform.data.batch import META_FILENAME, count_images, count_label_files, read_meta, write_meta


def organize_batch(batch_dir: Path, *, task: str | None = None) -> dict[str, Any]:
    """生成整理报告并合并进 batch.meta.yaml。"""
    batch_dir = batch_dir.resolve()
    if not batch_dir.is_dir():
        raise FileNotFoundError(batch_dir)

    images = count_images(batch_dir / "images") + count_images(batch_dir / "images" / "train")
    labels = count_label_files(batch_dir / "labels") + count_label_files(batch_dir / "labels" / "train")

    report: dict[str, Any] = {
        "task": task,
        "images": images,
        "labels": labels,
        "pair_ratio": round(labels / images, 3) if images else 0,
        "ready_for_ingest": images > 0 and labels > 0,
        "issues": [],
    }
    if images and not labels:
        report["issues"].append("missing_labels")
    if labels and not images:
        report["issues"].append("missing_images")

    meta = read_meta(batch_dir) or {}
    meta["organize_report"] = report
    meta.setdefault("counts", {})
    meta["counts"]["images"] = images
    meta["counts"]["labels"] = labels
    write_meta(batch_dir, meta)
    return report

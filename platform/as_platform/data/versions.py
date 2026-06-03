"""数据集版本管理 — snapshot / diff / lineage。版本以 JSON 文件存储在 datasets/<project>/versions/。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from as_platform.config import WORKSPACE
from as_platform.data.core import get_catalog


def _versions_dir(project: str) -> Path:
    return WORKSPACE / "datasets" / project / "versions"


def list_versions(project: str = "dms") -> list[dict[str, Any]]:
    """列出所有版本，按时间倒序。"""
    vdir = _versions_dir(project)
    if not vdir.is_dir():
        return []
    versions: list[dict[str, Any]] = []
    for f in sorted(vdir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_id"] = f.stem
            versions.append(data)
        except Exception:
            pass
    return versions


def get_version(project: str, version_id: str) -> dict[str, Any] | None:
    vf = _versions_dir(project) / f"{version_id}.json"
    if not vf.is_file():
        return None
    data = json.loads(vf.read_text(encoding="utf-8"))
    data["_id"] = vf.stem
    return data


def create_snapshot(project: str, description: str = "", author: str = "") -> dict[str, Any]:
    """基于当前 catalog 创建数据集快照。"""
    catalog = get_catalog(refresh=True)
    dms = catalog.get("dms", {})
    lane = catalog.get("lane", {})

    # Collect pack summary from catalog
    packs_summary: dict[str, dict[str, Any]] = {}
    all_batches: list[str] = []
    total_images = 0
    total_labels = 0

    if project == "dms":
        for task_id, entry in dms.items():
            entry_d = entry if isinstance(entry, dict) else {}
            for p in entry_d.get("packs", []) or []:
                pname = p.get("name", "")
                if pname not in packs_summary:
                    packs_summary[pname] = {
                        "train_images": 0, "val_images": 0, "test_images": 0,
                        "class_counts": {}, "tasks": [],
                    }
                s = packs_summary[pname]
                s["train_images"] += p.get("train_images", 0) or 0
                s["val_images"] += p.get("val_images", 0) or 0
                s["test_images"] += p.get("test_images", 0) or 0
                if task_id not in s["tasks"]:
                    s["tasks"].append(task_id)
                total_images += (p.get("train_images", 0) or 0) + (p.get("val_images", 0) or 0)
                total_labels += p.get("label_files", 0) or 0

        # Collect batch names from pending report
        from as_platform.data.core import get_pending_report
        report = get_pending_report()
        for b in report.get("batches", []) or []:
            if isinstance(b, dict) and b.get("project") == "dms":
                all_batches.append(b.get("batch", ""))

    # Determine version number
    existing = list_versions(project)
    version_num = len(existing) + 1
    version_id = f"v{version_num}"

    # Get parent version
    parent_id = existing[0]["_id"] if existing else None

    # Compute diff if parent exists
    diff: dict[str, Any] | None = None
    if parent_id and existing:
        parent = existing[0]
        parent_packs = set((parent.get("packs") or {}).keys())
        current_packs = set(packs_summary.keys())
        parent_batches = set(parent.get("batches", []) or [])
        current_batches = set(all_batches)
        diff = {
            "added_packs": sorted(current_packs - parent_packs),
            "removed_packs": sorted(parent_packs - current_packs),
            "added_batches": sorted(current_batches - parent_batches),
            "removed_batches": sorted(parent_batches - current_batches),
        }

    snapshot = {
        "version_id": version_id,
        "project": project,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "author": author,
        "parent_version": parent_id,
        "summary": {
            "packs_count": len(packs_summary),
            "total_images": total_images,
            "total_labels": total_labels,
            "batches_count": len(all_batches),
        },
        "packs": packs_summary,
        "batches": sorted(all_batches),
        "diff": diff,
    }

    # Save to file
    vdir = _versions_dir(project)
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / f"{version_id}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    snapshot["_id"] = version_id
    return snapshot


def diff_versions(project: str, v1: str, v2: str) -> dict[str, Any]:
    """对比两个版本。"""
    a = get_version(project, v1)
    b = get_version(project, v2)
    if not a or not b:
        return {"error": "版本不存在"}

    a_packs = set((a.get("packs") or {}).keys())
    b_packs = set((b.get("packs") or {}).keys())

    pack_changes: list[dict[str, Any]] = []
    for pname in a_packs | b_packs:
        pa = (a.get("packs") or {}).get(pname, {})
        pb = (b.get("packs") or {}).get(pname, {})
        if pa != pb:
            pack_changes.append({
                "pack": pname,
                "v1": {"train": pa.get("train_images", 0), "val": pa.get("val_images", 0)},
                "v2": {"train": pb.get("train_images", 0), "val": pb.get("val_images", 0)},
            })

    return {
        "v1": {"id": v1, "created": a.get("created_at"), "total": a.get("summary", {}).get("total_images", 0)},
        "v2": {"id": v2, "created": b.get("created_at"), "total": b.get("summary", {}).get("total_images", 0)},
        "added_packs": sorted(b_packs - a_packs),
        "removed_packs": sorted(a_packs - b_packs),
        "pack_changes": pack_changes,
        "image_delta": (b.get("summary", {}).get("total_images", 0) or 0) - (a.get("summary", {}).get("total_images", 0) or 0),
    }

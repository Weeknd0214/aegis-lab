"""Catalog cache: memory/disk + cheap directory-change invalidation."""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

from as_platform.config import WORKSPACE

CATALOG_CACHE_FILE = WORKSPACE / "manifests" / "catalog_cache.json"
CATALOG_CACHE_TTL_SEC = int(os.environ.get("AS_CATALOG_CACHE_TTL_SEC", "300"))
CATALOG_USE_REPORTS = os.environ.get("AS_CATALOG_USE_REPORTS", "1").lower() in ("1", "true", "yes")
CATALOG_CACHE_VERSION = 3

REPORTS_DIR = WORKSPACE / "reports"
DMS_SUMMARY_CSV = REPORTS_DIR / "dms_task_image_summary.csv"
DMS_CLASS_CSV = REPORTS_DIR / "dms_task_class_image_counts.csv"

_CATALOG_MEM_CACHE: dict[str, Any] | None = None


def invalidate_catalog_cache() -> None:
    global _CATALOG_MEM_CACHE
    _CATALOG_MEM_CACHE = None
    if CATALOG_CACHE_FILE.is_file():
        try:
            CATALOG_CACHE_FILE.unlink()
        except OSError:
            pass


def _dir_fingerprint(path: Path, *, scan_children: bool = True) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "missing": True}
    try:
        st = path.stat()
        fp: dict[str, Any] = {
            "path": str(path),
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
        }
        if scan_children and path.is_dir():
            children: list[dict[str, Any]] = []
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        if entry.name.startswith("."):
                            continue
                        try:
                            est = entry.stat(follow_symlinks=False)
                            children.append(
                                {
                                    "name": entry.name,
                                    "mtime_ns": est.st_mtime_ns,
                                    "is_dir": entry.is_dir(follow_symlinks=False),
                                }
                            )
                        except OSError:
                            children.append({"name": entry.name, "error": True})
            except OSError:
                fp["scan_error"] = True
            children.sort(key=lambda x: x.get("name", ""))
            fp["children"] = children
        return fp
    except OSError:
        return {"path": str(path), "error": True}


def build_catalog_signature(wf: dict, proj_root_fn) -> dict[str, Any]:
    """Cheap signature: config files + inbox/pack directory mtimes (auto-invalidate on drop)."""
    from as_platform.data.core import _pack_registry_path, load_pack_registry

    files: list[dict[str, Any]] = []
    for rel in ("workflow.registry.yaml",):
        p = WORKSPACE / rel
        try:
            st = p.stat()
            files.append({"path": str(p), "mtime_ns": st.st_mtime_ns, "size": st.st_size})
        except FileNotFoundError:
            files.append({"path": str(p), "missing": True})

    dirs: list[dict[str, Any]] = []
    for pname in ("dms", "lane"):
        root = proj_root_fn(wf, pname)
        dirs.append(_dir_fingerprint(root, scan_children=False))
        dirs.append(_dir_fingerprint(root / "inbox"))
        try:
            packs_reg = load_pack_registry(pname, root, wf)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            packs_reg = {"packs": []}
        dirs.append(_dir_fingerprint(root / "packs", scan_children=False))
        for p in packs_reg.get("packs", []):
            pack_path = root / p.get("path", p.get("name", ""))
            dirs.append(_dir_fingerprint(pack_path, scan_children=False))
        if pname == "dms":
            for cfg_path in (
                root / wf["projects"]["dms"]["registry"],
                root / "manifests" / "dataset_class_summary.txt",
                _pack_registry_path("dms", root, wf),
            ):
                try:
                    st = cfg_path.stat()
                    files.append({"path": str(cfg_path), "mtime_ns": st.st_mtime_ns, "size": st.st_size})
                except FileNotFoundError:
                    files.append({"path": str(cfg_path), "missing": True})
            reg_path = root / wf["projects"]["dms"]["registry"]
            if reg_path.is_file():
                import yaml

                reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
                for task in (reg.get("tasks") or {}).keys():
                    dirs.append(_dir_fingerprint(root / "inbox" / task))
        if pname == "lane":
            dirs.append(_dir_fingerprint(_pack_registry_path("lane", root, wf), scan_children=False))

    for csv_path in (DMS_SUMMARY_CSV, DMS_CLASS_CSV):
        try:
            st = csv_path.stat()
            files.append({"path": str(csv_path), "mtime_ns": st.st_mtime_ns, "size": st.st_size})
        except FileNotFoundError:
            files.append({"path": str(csv_path), "missing": True})

    return {"files": files, "dirs": dirs}


def load_disk_cache() -> dict[str, Any] | None:
    if not CATALOG_CACHE_FILE.is_file():
        return None
    try:
        return json.loads(CATALOG_CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_disk_cache(payload: dict[str, Any]) -> None:
    CATALOG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _catalog_has_empty_bbox(catalog: dict[str, Any]) -> bool:
    for task in (catalog.get("dms") or {}).values():
        for pack in task.get("packs") or []:
            boxes = int(pack.get("total_boxes") or 0)
            pts = pack.get("bbox_points") or []
            if boxes > 0 and not pts:
                return True
    return False


def get_cached_catalog(signature: dict[str, Any], *, refresh: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (catalog_data, meta). meta describes cache hit/miss."""
    global _CATALOG_MEM_CACHE
    now = time.time()
    meta: dict[str, Any] = {"cached": False, "source": "scan"}

    if refresh:
        _CATALOG_MEM_CACHE = None
        return None, meta

    for source, cache in (("memory", _CATALOG_MEM_CACHE), ("disk", load_disk_cache() if not _CATALOG_MEM_CACHE else None)):
        if not cache:
            continue
        age = now - float(cache.get("generated_at_ts", 0.0))
        if cache.get("signature") != signature:
            continue
        if cache.get("version") != CATALOG_CACHE_VERSION:
            continue
        data = cache.get("data") or {}
        if _catalog_has_empty_bbox(data):
            continue
        if age > CATALOG_CACHE_TTL_SEC:
            continue
        if source == "disk":
            _CATALOG_MEM_CACHE = cache
        meta = {
            "cached": True,
            "cache_source": source,
            "cache_age_sec": round(age, 1),
            "generated_at_ts": cache.get("generated_at_ts"),
            "build_source": cache.get("build_source", "scan"),
        }
        return cache.get("data", {}), meta

    return None, meta


def store_catalog_cache(signature: dict[str, Any], data: dict[str, Any], *, build_source: str = "scan") -> dict[str, Any]:
    global _CATALOG_MEM_CACHE
    now = time.time()
    payload = {
        "version": CATALOG_CACHE_VERSION,
        "generated_at_ts": now,
        "signature": signature,
        "build_source": build_source,
        "data": data,
    }
    _CATALOG_MEM_CACHE = payload
    save_disk_cache(payload)
    return payload


def load_dms_reports() -> tuple[dict[tuple[str, str], dict[str, int]], dict[str, dict[str, int]]] | None:
    """Parse precomputed CSV reports: (task, pack) -> splits, task -> class_counts."""
    if not CATALOG_USE_REPORTS or not DMS_SUMMARY_CSV.is_file():
        return None

    splits: dict[tuple[str, str], dict[str, int]] = {}
    try:
        with DMS_SUMMARY_CSV.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                task = row.get("任务", "").strip()
                pack = row.get("数据包", "").strip() or "default"
                if not task:
                    continue
                splits[(task, pack)] = {
                    "train": int(row.get("训练集图片") or 0),
                    "val": int(row.get("验证集图片") or 0),
                    "test": int(row.get("测试集图片") or 0),
                    "total": int(row.get("图片总数") or 0),
                }
    except (OSError, ValueError, csv.Error):
        return None

    class_by_task: dict[str, dict[str, int]] = {}
    if DMS_CLASS_CSV.is_file():
        try:
            with DMS_CLASS_CSV.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    task = row.get("任务", "").strip()
                    cls_name = row.get("类别名", "").strip()
                    if not task or not cls_name:
                        continue
                    try:
                        cnt = int(row.get("含该类别图片数") or 0)
                    except ValueError:
                        continue
                    class_by_task.setdefault(task, {})[cls_name] = cnt
        except (OSError, ValueError, csv.Error):
            pass

    if not splits:
        return None
    return splits, class_by_task

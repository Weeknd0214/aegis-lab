"""平台共享逻辑：pending、catalog、register-batch。"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from as_platform.config import WORKSPACE, WORKSPACE_ROOT, LANE_DATA_VIZ_ENABLED
from as_platform.data.batch import META_FILENAME, dms_has_images, enrich_batch, write_meta
from as_platform.data.catalog_cache import (
    build_catalog_signature,
    get_cached_catalog,
    invalidate_catalog_cache,
    load_dms_reports,
    store_catalog_cache,
)

import sys as _sys

def _dms_scripts_dir() -> Path:
    for cand in (
        WORKSPACE / "datasets" / "dms" / "scripts",
        WORKSPACE / "datasets" / "dms.embedded.bak" / "scripts",
    ):
        if (cand / "task_registry.py").is_file():
            return cand
    return WORKSPACE / "datasets" / "dms" / "scripts"


_DMS_SCRIPTS = _dms_scripts_dir()
if str(_DMS_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_DMS_SCRIPTS))
from task_registry import (  # noqa: E402
    DOMAIN_LABELS,
    get_mode_config,
    inbox_dir,
    iter_catalog_tasks,
    report_task_key,
    task_defs_for_pending,
)

MAX_LABEL_FILES_PER_PACK = 2000
MAX_BBOX_POINTS_PER_PACK = 1500
MAX_LANE_MASK_SAMPLES_PER_PACK = 500
LANE_Y_BINS = 12
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_wf() -> dict:
    return yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text(encoding="utf-8"))


def proj_root(wf: dict, name: str) -> Path:
    return (WORKSPACE / wf["projects"][name]["root"]).resolve()


def load_pack_registry(project: str, root: Path, wf: dict) -> dict:
    pcfg = wf["projects"][project]
    reg_file = root / pcfg.get("packs_registry", "datasets_registry.json")
    if reg_file.suffix in (".yaml", ".yml"):
        return yaml.safe_load(reg_file.read_text(encoding="utf-8"))
    return json.loads(reg_file.read_text(encoding="utf-8"))


def _pack_registry_path(project: str, root: Path, wf: dict) -> Path:
    pcfg = wf["projects"][project]
    return root / pcfg.get("packs_registry", "datasets_registry.json")


def resolve_pack(project: str, root: Path, wf: dict, name: str) -> str:
    reg = load_pack_registry(project, root, wf)
    name = reg.get("aliases", {}).get(name, name)
    for p in reg.get("packs", []):
        if p.get("name") == name:
            return p.get("path", name)
    if (root / name).is_dir():
        return name
    known = [p.get("name") for p in reg.get("packs", [])]
    raise ValueError(f"[{project}] 未知包: {name}，已登记: {known}")


def _pack_dir_usable(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def _dms_workspace_pack_dir(pack_name: str) -> Path | None:
    ws = WORKSPACE_ROOT
    if ws is None:
        return None
    cand = ws / "DMS/DATASET/packs" / pack_name
    return cand if _pack_dir_usable(cand) else None


def resolve_pack_dir(project: str, root: Path, wf: dict, name: str) -> Path:
    rel = resolve_pack(project, root, wf, name)
    primary = root / rel
    if _pack_dir_usable(primary):
        return primary.resolve()
    reg = load_pack_registry(project, root, wf)
    pack_name = reg.get("aliases", {}).get(name, name)
    if project == "dms":
        fallback = _dms_workspace_pack_dir(pack_name)
        if fallback is not None:
            return fallback
    try:
        return primary.resolve()
    except OSError:
        return primary


def _read_jsonl_tail(path: Path, n: int = 10) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def get_pending_report(wf: dict | None = None) -> dict[str, Any]:
    wf = wf or load_wf()
    report: dict[str, Any] = {
        "workspace": str(WORKSPACE),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "projects": {},
        "batches": [],
    }

    for pname, pcfg in wf["projects"].items():
        root = proj_root(wf, pname)
        active = set(pcfg.get("active_packs", []))
        try:
            reg_all = load_pack_registry(pname, root, wf)
        except (FileNotFoundError, json.JSONDecodeError):
            reg_all = {"packs": []}
        all_names = {p["name"] for p in reg_all.get("packs", [])}
        not_active = sorted(all_names - active)

        proj: dict[str, Any] = {
            "root": str(root),
            "active_packs": list(active),
            "not_enabled": not_active,
            "tasks": {},
            "task_defs": {},
        }

        if pname == "dms":
            reg_path = root / pcfg["registry"]
            reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
            src_sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
            ingest_log = root / "manifests" / "ingest_log.jsonl"
            proj["recent_ingest"] = _read_jsonl_tail(ingest_log, 10)

            proj["task_defs"] = task_defs_for_pending(reg)

            def _scan_task_inbox(task_id: str, mode: str | None) -> list[str]:
                ib = inbox_dir(root, task_id, mode, reg)
                if not ib.is_dir():
                    return []
                subdirs = [
                    d.name for d in ib.iterdir() if d.is_dir() and not d.name.startswith(".")
                ]
                if subdirs:
                    return subdirs
                tcfg = reg.get("tasks", {}).get(task_id, {})
                if tcfg.get("type") == "multi" and mode:
                    if dms_has_images(ib):
                        return [mode]
                return []

            def _multi_inbox_batch_rows(task: str, mode: str) -> list[dict[str, Any]]:
                """multi 任务：inbox 可能即批次根目录（如 inbox/dam/batch_0516）。"""
                ib = inbox_dir(root, task, mode, reg)
                if not ib.is_dir():
                    return []
                rows: list[dict[str, Any]] = []
                subdirs = [
                    d.name for d in ib.iterdir() if d.is_dir() and not d.name.startswith(".")
                ]
                if subdirs:
                    for batch_name in subdirs:
                        row = enrich_batch(
                            ib / batch_name,
                            project="dms",
                            task=task,
                            pack=None,
                            batch=batch_name,
                            location="inbox",
                        )
                        row["mode"] = mode
                        rows.append(row)
                elif dms_has_images(ib) or (ib / META_FILENAME).is_file():
                    row = enrich_batch(
                        ib,
                        project="dms",
                        task=task,
                        pack=None,
                        batch=mode,
                        location="inbox",
                    )
                    row["mode"] = mode
                    rows.append(row)
                return rows

            def _scan_sources(task_id: str, mode: str | None) -> dict[str, list[str]]:
                mcfg = get_mode_config(task_id, mode, reg)
                pending: dict[str, list[str]] = {}
                for pack_name in all_names:
                    try:
                        pack_dir = resolve_pack_dir("dms", root, wf, pack_name)
                    except ValueError:
                        continue
                    src_root = pack_dir / mcfg["task_dir"] / src_sub
                    if src_root.is_dir():
                        batches = [
                            d.name for d in src_root.iterdir()
                            if d.is_dir()
                            and d.name not in ("_ingested", "_merged")
                            and not d.name.startswith(".")
                        ]
                        if batches:
                            pending[pack_name] = batches
                return pending

            for task, tcfg in reg.get("tasks", {}).items():
                if tcfg.get("type") == "multi":
                    task_inbox: dict[str, list[str]] = {}
                    task_sources: dict[str, dict[str, list[str]]] = {}
                    for mode in (tcfg.get("modes") or {}):
                        task_inbox[mode] = _scan_task_inbox(task, mode)
                        task_sources[mode] = _scan_sources(task, mode)
                        for row in _multi_inbox_batch_rows(task, mode):
                            report["batches"].append(row)
                        for pack_name, batch_list in task_sources[mode].items():
                            pack_dir = resolve_pack_dir("dms", root, wf, pack_name)
                            src_root = pack_dir / get_mode_config(task, mode, reg)["task_dir"] / src_sub
                            for batch_name in batch_list:
                                row = enrich_batch(
                                    src_root / batch_name,
                                    project="dms",
                                    task=task,
                                    pack=pack_name,
                                    batch=batch_name,
                                    location="sources",
                                )
                                row["mode"] = mode
                                report["batches"].append(row)
                    proj["tasks"][task] = {"inbox": task_inbox, "sources": task_sources}
                else:
                    inbox_batches = _scan_task_inbox(task, None)
                    sources_pending = _scan_sources(task, None)
                    proj["tasks"][task] = {"inbox": inbox_batches, "sources": sources_pending}
                    ib = inbox_dir(root, task, None, reg)
                    for batch_name in inbox_batches:
                        report["batches"].append(
                            enrich_batch(
                                ib / batch_name,
                                project="dms",
                                task=task,
                                pack=None,
                                batch=batch_name,
                                location="inbox",
                            )
                        )
                    for pack_name, batch_list in sources_pending.items():
                        pack_dir = resolve_pack_dir("dms", root, wf, pack_name)
                        src_root = pack_dir / tcfg["task_dir"] / src_sub
                        for batch_name in batch_list:
                            report["batches"].append(
                                enrich_batch(
                                    src_root / batch_name,
                                    project="dms",
                                    task=task,
                                    pack=pack_name,
                                    batch=batch_name,
                                    location="sources",
                                )
                            )

        if pname == "adas":
            inbox_adas = root / "inbox"
            if inbox_adas.is_dir():
                for task_dir in sorted(inbox_adas.iterdir()):
                    if not task_dir.is_dir() or task_dir.name.startswith("."):
                        continue
                    for batch_dir in sorted(task_dir.iterdir()):
                        if not batch_dir.is_dir() or batch_dir.name.startswith("."):
                            continue
                        report["batches"].append(
                            enrich_batch(
                                batch_dir,
                                project="adas",
                                task=task_dir.name,
                                pack=None,
                                batch=batch_dir.name,
                                location="inbox",
                            )
                        )

        if pname == "lane":
            proj["packs"] = {}
            for pack_name in all_names:
                try:
                    path = resolve_pack("lane", root, wf, pack_name)
                except ValueError:
                    continue
                pack_path = root / path
                train_lines = 0
                tg = pack_path / "list" / "train_gt.txt"
                if tg.is_file():
                    train_lines = sum(1 for _ in tg.open(encoding="utf-8"))
                proj["packs"][pack_name] = {
                    "path": path,
                    "train_lines": train_lines,
                    "enabled": pack_name in active,
                }
                if pack_name in not_active and pack_path.is_dir():
                    report["batches"].append(
                        enrich_batch(
                            pack_path,
                            project="lane",
                            task=None,
                            pack=pack_name,
                            batch=path,
                            location="pack",
                        )
                    )

            for child in sorted(root.iterdir()) if root.is_dir() else []:
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if child.name in ("lists_merged", "scripts", "inbox"):
                    continue
                if not child.name.startswith("DATASET-AddBy-"):
                    continue
                if any(
                    p.get("path") == child.name or p.get("name") == child.name
                    for p in reg_all.get("packs", [])
                ):
                    continue
                report["batches"].append(
                    enrich_batch(
                        child,
                        project="lane",
                        task=None,
                        pack=None,
                        batch=child.name,
                        location="unregistered",
                    )
                )

            inbox_lane = root / "inbox"
            if inbox_lane.is_dir():
                for batch_dir in sorted(inbox_lane.iterdir()):
                    if batch_dir.is_dir() and not batch_dir.name.startswith("."):
                        report["batches"].append(
                            enrich_batch(
                                batch_dir,
                                project="lane",
                                task=None,
                                pack=None,
                                batch=batch_dir.name,
                                location="inbox",
                            )
                        )

        report["projects"][pname] = proj

    return report


def _parse_class_summary(text: str) -> dict[str, dict[str, int]]:
    """解析 dataset_class_summary.txt 按 task 的类统计。"""
    by_task: dict[str, dict[str, int]] = {}
    current_task: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(":") and " " not in line.rstrip(":"):
            current_task = line.rstrip(":")
            by_task.setdefault(current_task, {})
            continue
        if current_task and ":" in line:
            parts = line.split(":", 1)
            cls_name = parts[0].strip()
            try:
                count = int(re.search(r"\d+", parts[1]).group())  # type: ignore
                by_task[current_task][cls_name] = count
            except (AttributeError, ValueError):
                pass
    return by_task


def _class_name_map(tcfg: dict[str, Any]) -> dict[int, str]:
    names = tcfg.get("names")
    if isinstance(names, list):
        return {idx: str(name) for idx, name in enumerate(names)}
    if isinstance(names, dict):
        out: dict[int, str] = {}
        for k, v in names.items():
            try:
                out[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def _count_images_in_dir(img_dir: Path) -> int:
    if not img_dir.is_dir():
        return 0
    total = 0
    try:
        with os.scandir(img_dir) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=True):
                    continue
                if Path(entry.name).suffix.lower() in IMAGE_EXTS:
                    total += 1
    except OSError:
        return 0
    return total


def _count_split_images(task_data: Path) -> dict[str, int]:
    counts = {
        "train": _count_images_in_dir(task_data / "images" / "train"),
        "val": _count_images_in_dir(task_data / "images" / "val"),
        "test": _count_images_in_dir(task_data / "images" / "test"),
    }
    if sum(counts.values()) == 0:
        flat = _count_images_in_dir(task_data / "images")
        if flat:
            counts["train"] = flat
    return counts


def _iter_label_files(label_dirs: list[Path]):
    for label_dir in label_dirs:
        if not label_dir.is_dir():
            continue
        try:
            with os.scandir(label_dir) as it:
                stack = [entry.path for entry in it if entry.is_dir(follow_symlinks=True)]
                files = [entry.path for entry in it if entry.is_file(follow_symlinks=True) and entry.name.endswith(".txt")]
        except OSError:
            continue
        for fp in files:
            yield Path(fp)
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=True):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=True) and entry.name.endswith(".txt"):
                            yield Path(entry.path)
            except OSError:
                continue


def _label_dirs_for_task(task_data: Path) -> list[Path]:
    return [task_data / "labels" / "train", task_data / "labels" / "val", task_data / "labels"]


def _task_data_has_labels(task_data: Path) -> bool:
    return any(p.is_dir() for p in _label_dirs_for_task(task_data))


def resolve_task_data_for_scan(pack_dir: Path, task_dir: str) -> Path:
    """解析可扫描的 task 数据目录。

    DAM 等批次在宿主机上常为指向绝对路径的 symlink，Docker 内 resolve() 会落到
    容器外路径导致 is_dir() 为 False、bbox 采样为空。此处回映射到 AS_WORKSPACE_ROOT
    并尝试 pack 级 _dam_stash_* 目录。
    """
    task_data = pack_dir / task_dir
    if _task_data_has_labels(task_data):
        return task_data

    if task_data.is_symlink():
        try:
            raw = os.readlink(task_data)
            link = Path(raw)
            candidates: list[Path] = []
            if link.is_absolute():
                s = str(link).replace("\\", "/")
                for marker in ("DMS/DATASET/", "DMS/DATASET"):
                    idx = s.find(marker)
                    if idx >= 0 and WORKSPACE_ROOT:
                        candidates.append(WORKSPACE_ROOT / s[idx:])
            else:
                candidates.append((task_data.parent / link).resolve())
            for cand in candidates:
                if _task_data_has_labels(cand):
                    return cand
        except OSError:
            pass

    leaf = Path(task_dir).name
    if leaf.startswith("batch_"):
        stash = pack_dir / f"_dam_stash_{leaf.split('_', 1)[1]}"
        if _task_data_has_labels(stash):
            return stash

    return task_data


def _parse_bbox_wh(parts: list[str]) -> list[float] | None:
    if len(parts) < 5:
        return None
    try:
        w = float(parts[3])
        h = float(parts[4])
        if 0.0 < w <= 1.0 and 0.0 < h <= 1.0:
            return [round(w, 6), round(h, 6)]
    except ValueError:
        return None
    return None


def _collect_bbox_points_sample(task_data: Path, *, max_points: int = MAX_BBOX_POINTS_PER_PACK) -> list[list[float]]:
    """Lightweight sample for scatter plot; does not scan images."""
    bbox_points: list[list[float]] = []
    remaining_files = MAX_LABEL_FILES_PER_PACK
    for txt in _iter_label_files(_label_dirs_for_task(task_data)):
        if len(bbox_points) >= max_points or remaining_files <= 0:
            break
        remaining_files -= 1
        try:
            for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                if len(bbox_points) >= max_points:
                    break
                line = line.strip()
                if not line:
                    continue
                wh = _parse_bbox_wh(line.split())
                if wh:
                    bbox_points.append(wh)
        except OSError:
            continue
    return bbox_points


def _collect_pack_label_distribution(task_data: Path, tcfg: dict[str, Any]) -> dict[str, Any]:
    label_dirs = _label_dirs_for_task(task_data)
    class_counts: dict[int, int] = {}
    bbox_points: list[list[float]] = []
    parsed_files = 0
    sampled = False
    remaining = MAX_LABEL_FILES_PER_PACK
    for txt in _iter_label_files(label_dirs):
        if remaining <= 0:
            sampled = True
            break
        remaining -= 1
        parsed_files += 1
        try:
            for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                cls_token = line.split(maxsplit=1)[0]
                cls_id = int(float(cls_token))
                class_counts[cls_id] = class_counts.get(cls_id, 0) + 1
                parts = line.split()
                if len(bbox_points) < MAX_BBOX_POINTS_PER_PACK:
                    wh = _parse_bbox_wh(parts)
                    if wh:
                        bbox_points.append(wh)
        except OSError:
            continue

    name_map = _class_name_map(tcfg)
    by_name: dict[str, int] = {}
    for cls_id, cnt in sorted(class_counts.items(), key=lambda x: x[1], reverse=True):
        key = name_map.get(cls_id, f"class_{cls_id}")
        by_name[key] = cnt
    return {
        "class_counts": by_name,
        "label_files": parsed_files,
        "sampled": sampled,
        "total_boxes": sum(class_counts.values()),
        "bbox_points": bbox_points,
    }


def _histogram(values: list[float], bins: list[float]) -> list[dict[str, float]]:
    if len(bins) < 2:
        return []
    counts = [0] * (len(bins) - 1)
    for v in values:
        for i in range(len(bins) - 1):
            lo, hi = bins[i], bins[i + 1]
            if (v >= lo and v < hi) or (i == len(bins) - 2 and v >= lo and v <= hi):
                counts[i] += 1
                break
    return [
        {"left": bins[i], "right": bins[i + 1], "count": counts[i]}
        for i in range(len(counts))
    ]


def _extract_lane_mask_stats(mask_path: Path) -> dict[str, Any] | None:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return None

    try:
        img = Image.open(mask_path).convert("L")
    except OSError:
        return None

    w, h = img.size
    pix = img.load()
    if pix is None:
        return None

    lane_bins: dict[int, list[dict[str, float]]] = {}
    present_ids: set[int] = set()
    for y in range(h):
        by_id: dict[int, tuple[int, int]] = {}
        for x in range(w):
            lane_id = int(pix[x, y])
            if lane_id <= 0:
                continue
            present_ids.add(lane_id)
            if lane_id not in by_id:
                by_id[lane_id] = (x, x)
            else:
                mn, mx = by_id[lane_id]
                if x < mn:
                    mn = x
                if x > mx:
                    mx = x
                by_id[lane_id] = (mn, mx)
        if not by_id:
            continue
        y_bin = min(LANE_Y_BINS - 1, int((y / max(1, h - 1)) * LANE_Y_BINS))
        for lane_id, (mn, mx) in by_id.items():
            bucket = lane_bins.setdefault(lane_id, [dict(min_x=1e9, max_x=-1e9, count=0) for _ in range(LANE_Y_BINS)])
            cur = bucket[y_bin]
            cur["min_x"] = min(cur["min_x"], float(mn))
            cur["max_x"] = max(cur["max_x"], float(mx))
            cur["count"] += 1

    lengths: list[float] = []
    curvatures: list[float] = []
    for lane_id in sorted(present_ids):
        bins = lane_bins.get(lane_id, [])
        centers: list[tuple[float, float]] = []
        for i, b in enumerate(bins):
            if b["count"] <= 0:
                continue
            center_x = (b["min_x"] + b["max_x"]) / 2.0
            center_y = ((i + 0.5) / LANE_Y_BINS) * h
            centers.append((center_x, center_y))
        if len(centers) < 2:
            continue
        length = 0.0
        for i in range(1, len(centers)):
            dx = centers[i][0] - centers[i - 1][0]
            dy = centers[i][1] - centers[i - 1][1]
            length += math.sqrt(dx * dx + dy * dy)
        lengths.append(length)

        if len(centers) >= 3:
            second_diffs = []
            xs = [c[0] for c in centers]
            for i in range(1, len(xs) - 1):
                second_diffs.append(abs(xs[i + 1] - 2 * xs[i] + xs[i - 1]))
            if second_diffs:
                curvatures.append(sum(second_diffs) / len(second_diffs))

    return {
        "lane_count": len(present_ids),
        "lengths": lengths,
        "curvatures": curvatures,
    }


def _collect_lane_quality(pack_path: Path) -> dict[str, Any]:
    list_files = [pack_path / "list" / "train_gt.txt", pack_path / "list" / "val_gt.txt"]
    entries: list[Path] = []
    for lf in list_files:
        if not lf.is_file():
            continue
        try:
            for line in lf.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                entries.append(pack_path / parts[1])
                if len(entries) >= MAX_LANE_MASK_SAMPLES_PER_PACK:
                    break
        except OSError:
            continue
        if len(entries) >= MAX_LANE_MASK_SAMPLES_PER_PACK:
            break

    lane_counts: list[float] = []
    lane_lengths: list[float] = []
    lane_curvatures: list[float] = []
    processed = 0
    for ann in entries:
        s = _extract_lane_mask_stats(ann)
        if not s:
            continue
        processed += 1
        lane_counts.append(float(s["lane_count"]))
        lane_lengths.extend(float(x) for x in s["lengths"])
        lane_curvatures.extend(float(x) for x in s["curvatures"])

    lane_count_hist: dict[str, int] = {}
    for c in lane_counts:
        key = str(int(c)) if c < 8 else "8+"
        lane_count_hist[key] = lane_count_hist.get(key, 0) + 1

    return {
        "analyzed_frames": processed,
        "lane_count_hist": lane_count_hist,
        "length_hist": _histogram(lane_lengths, [0, 60, 120, 180, 240, 320, 420, 560, 760, 1024]),
        "curvature_hist": _histogram(lane_curvatures, [0, 1, 2, 4, 6, 8, 12, 16, 24, 40]),
    }


def _catalog_signature(wf: dict) -> dict[str, Any]:
    return build_catalog_signature(wf, proj_root)


def _merge_multi_task_entry(
    dms: dict[str, Any],
    task_id: str,
    tcfg: dict,
    legacy_modes: dict[str, dict],
) -> None:
    entry = dms.setdefault(task_id, {})
    entry["type"] = "multi"
    entry["domain"] = tcfg.get("domain", "dms")
    entry["label"] = tcfg.get("label", task_id)
    entry["domain_label"] = DOMAIN_LABELS.get(tcfg.get("domain", "dms"), tcfg.get("domain", "dms"))
    modes = entry.setdefault("modes", {})
    for mode, mcfg in (tcfg.get("modes") or {}).items():
        mode_entry = modes.setdefault(mode, {})
        mode_entry.setdefault("label", mcfg.get("label", mode))
        mode_entry.setdefault("type", mcfg.get("type", "detect"))
        mode_entry.setdefault("nc", mcfg.get("nc"))
        mode_entry.setdefault("names", mcfg.get("names"))
        mode_entry.setdefault("packs", [])
        mode_entry.setdefault("class_counts", {})
        if mode in legacy_modes:
            leg = legacy_modes[mode]
            if not mode_entry.get("packs") and leg.get("packs"):
                mode_entry["packs"] = leg["packs"]
            if not mode_entry.get("class_counts") and leg.get("class_counts"):
                mode_entry["class_counts"] = leg["class_counts"]
    stray = entry.pop("packs", None)
    first_mode = next(iter(modes), None)
    if stray and isinstance(stray, list) and first_mode and not modes[first_mode].get("packs"):
        modes[first_mode]["packs"] = stray
    entry.pop("nc", None)
    entry.pop("names", None)


def _normalize_catalog_dms(dms: dict[str, Any], reg: dict) -> dict[str, Any]:
    """修复旧缓存：isa/isa_class→forward；dam_0417→dam；补全 multi 结构。"""
    if not dms:
        return dms
    tasks_cfg = (reg or {}).get("tasks") or {}

    legacy_forward = {}
    for old_key, mode in (("isa", "detect"), ("isa_class", "classify")):
        if old_key in dms:
            legacy_forward[mode] = dms.pop(old_key)
    fwd_cfg = tasks_cfg.get("forward") or {}
    if fwd_cfg.get("type") == "multi" or legacy_forward:
        _merge_multi_task_entry(dms, "forward", fwd_cfg, legacy_forward)

    legacy_dam: dict[str, dict] = {}
    if "dam_0417" in dms:
        legacy_dam["batch_0417"] = dms.pop("dam_0417")
    if "dam" in dms and (tasks_cfg.get("dam") or {}).get("type") == "multi":
        old_dam = dms.pop("dam")
        if old_dam.get("modes"):
            dms["dam"] = old_dam
        else:
            legacy_dam["batch_0516"] = old_dam
    dam_cfg = tasks_cfg.get("dam") or {}
    if dam_cfg.get("type") == "multi" or legacy_dam:
        _merge_multi_task_entry(dms, "dam", dam_cfg, legacy_dam)

    return dms


def _build_catalog(wf: dict, *, prefer_reports: bool = True) -> tuple[dict[str, Any], str]:
    out: dict[str, Any] = {"workspace": str(WORKSPACE), "dms": {}, "lane": {}}
    build_source = "scan"

    reports = load_dms_reports()
    report_splits: dict[tuple[str, str], dict[str, int]] = {}
    report_classes: dict[str, dict[str, int]] = {}
    if reports:
        report_splits, report_classes = reports
        build_source = "reports" if prefer_reports else "scan+reports"

    root = proj_root(wf, "dms")
    reg_path = root / wf["projects"]["dms"]["registry"]
    if not reg_path.is_file():
        out["dms_error"] = f"registry not found: {reg_path}"
        if report_splits:
            for (task, pack_name), rep in report_splits.items():
                entry = out["dms"].setdefault(task, {
                    "type": "unknown",
                    "class_counts": report_classes.get(task, {}),
                    "packs": [],
                })
                entry["packs"].append({
                    "name": pack_name,
                    "enabled": False,
                    "train_images": rep.get("train", 0),
                    "val_images": rep.get("val", 0),
                    "test_images": rep.get("test", 0),
                    "class_counts": report_classes.get(task, {}),
                    "label_files": 0,
                    "total_boxes": sum(report_classes.get(task, {}).values()) if task in report_classes else 0,
                    "sampled": True,
                    "bbox_points": [],
                })
        reg = {"tasks": {}}
    else:
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    try:
        packs_reg = load_pack_registry("dms", root, wf)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        packs_reg = {"packs": []}
    summary_path = root / "manifests" / "dataset_class_summary.txt"
    class_by_task = {}
    if summary_path.is_file():
        class_by_task = _parse_class_summary(summary_path.read_text(encoding="utf-8"))

    def _pack_row(task_id: str, mode: str | None, mcfg: dict, pack_name: str, p: dict, task_data: Path) -> dict[str, Any]:
        rep_key = report_task_key(task_id, mode)
        rep = report_splits.get((rep_key, pack_name))
        split_counts = _count_split_images(task_data)
        scan_total = sum(split_counts.values())
        if rep and (scan_total == 0 or not _task_data_has_labels(task_data)):
            split_counts = {"train": rep["train"], "val": rep["val"], "test": rep["test"]}
            class_counts = report_classes.get(rep_key, class_by_task.get(rep_key, {}))
            bbox_points = _collect_bbox_points_sample(task_data) if _task_data_has_labels(task_data) else []
            label_distribution = {
                "class_counts": class_counts,
                "label_files": 0,
                "sampled": True,
                "total_boxes": sum(class_counts.values()) if class_counts else 0,
                "bbox_points": bbox_points,
            }
        else:
            label_distribution = _collect_pack_label_distribution(task_data, mcfg)
            if not label_distribution["class_counts"] and rep_key in report_classes:
                label_distribution["class_counts"] = report_classes[rep_key]
            if scan_total == 0 and rep:
                split_counts = {"train": rep["train"], "val": rep["val"], "test": rep["test"]}
        return {
            "name": pack_name,
            "path": p.get("path"),
            "role": p.get("role"),
            "frozen": p.get("frozen", False),
            "enabled": pack_name in wf["projects"]["dms"].get("active_packs", []),
            "train_images": split_counts.get("train", 0),
            "val_images": split_counts.get("val", 0),
            "test_images": split_counts.get("test", 0),
            "class_counts": label_distribution["class_counts"],
            "label_files": label_distribution["label_files"],
            "total_boxes": label_distribution["total_boxes"],
            "sampled": label_distribution["sampled"],
            "bbox_points": label_distribution["bbox_points"],
        }

    for task, entry in iter_catalog_tasks(reg):
        tcfg = reg["tasks"][task]
        if tcfg.get("type") == "multi":
            entry["drop_paths"] = {
                **{
                    f"inbox_{mode}": str(inbox_dir(root, task, mode, reg).resolve())
                    for mode in (tcfg.get("modes") or {})
                },
                "sources_template": str((root / "packs" / "<pack>" / tcfg.get("task_dir", task) / "<subdir>" / "sources" / "<batch>").resolve()),
            }
            for mode in (tcfg.get("modes") or {}):
                mcfg = get_mode_config(task, mode, reg)
                mode_entry = entry["modes"][mode]
                rep_key = report_task_key(task, mode)
                mode_entry["class_counts"] = class_by_task.get("isa_detect", class_by_task.get(rep_key, {})) if mode == "detect" else class_by_task.get("isa_class_0116", class_by_task.get(rep_key, {}))
                if not mode_entry["class_counts"] and rep_key in report_classes:
                    mode_entry["class_counts"] = report_classes[rep_key]
                for p in packs_reg.get("packs", []):
                    pack_name = p["name"]
                    try:
                        pack_dir = resolve_pack_dir("dms", root, wf, pack_name)
                    except ValueError:
                        continue
                    task_data = resolve_task_data_for_scan(pack_dir, mcfg["task_dir"])
                    mode_entry["packs"].append(_pack_row(task, mode, mcfg, pack_name, p, task_data))
        else:
            entry["drop_paths"] = {
                "inbox": str(inbox_dir(root, task, None, reg).resolve()),
                "sources_template": str((root / "packs" / "<pack>" / tcfg.get("task_dir", task) / "sources" / "<batch>").resolve()),
            }
            rep_key = task
            if not entry["class_counts"]:
                entry["class_counts"] = class_by_task.get(task, report_classes.get(task, {}))
            for p in packs_reg.get("packs", []):
                pack_name = p["name"]
                try:
                    pack_dir = resolve_pack_dir("dms", root, wf, pack_name)
                except ValueError:
                    continue
                task_data = resolve_task_data_for_scan(pack_dir, tcfg.get("task_dir", task))
                entry["packs"].append(_pack_row(task, None, tcfg, pack_name, p, task_data))
            if not entry["class_counts"] and task in report_classes:
                entry["class_counts"] = report_classes[task]
        out["dms"][task] = entry

    out["dms"] = _normalize_catalog_dms(out["dms"], reg)

    root = proj_root(wf, "lane")
    try:
        reg = load_pack_registry("lane", root, wf)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        reg = {"packs": []}
    for p in reg.get("packs", []):
        pack_name = p["name"]
        path = p.get("path", pack_name)
        pack_path = root / path
        tg = pack_path / "list" / "train_gt.txt"
        vg = pack_path / "list" / "val_gt.txt"
        sg = pack_path / "list" / "test_gt.txt"
        lane_quality = _collect_lane_quality(pack_path) if LANE_DATA_VIZ_ENABLED else {}
        out["lane"][pack_name] = {
            "path": path,
            "role": p.get("role"),
            "frozen": p.get("frozen", False),
            "enabled": pack_name in wf["projects"]["lane"].get("active_packs", []),
            "train_lines": sum(1 for _ in tg.open(encoding="utf-8")) if tg.is_file() else 0,
            "val_lines": sum(1 for _ in vg.open(encoding="utf-8")) if vg.is_file() else 0,
            "test_lines": sum(1 for _ in sg.open(encoding="utf-8")) if sg.is_file() else 0,
            "drop_path": str(pack_path.resolve()),
            "add_template": "python as.py add lane --src <archive> --engineer <name> --date YYYYMMDD",
            "quality": lane_quality,
        }
    return out, build_source


def get_catalog(
    wf: dict | None = None,
    project: str | None = None,
    task_or_pack: str | None = None,
    *,
    refresh: bool = False,
) -> dict:
    wf = wf or load_wf()
    sig = _catalog_signature(wf)
    full_catalog, cache_meta = get_cached_catalog(sig, refresh=refresh)

    if not full_catalog:
        full_catalog, build_source = _build_catalog(wf, prefer_reports=not refresh)
        store_catalog_cache(sig, full_catalog, build_source=build_source)
        cache_meta = {"cached": False, "build_source": build_source}
    else:
        reg_path = proj_root(wf, "dms") / wf["projects"]["dms"]["registry"]
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) if reg_path.is_file() else {}
        dms = _normalize_catalog_dms(full_catalog.get("dms") or {}, reg)
        if dms != full_catalog.get("dms"):
            full_catalog = {**full_catalog, "dms": dms}

    result: dict[str, Any]
    if project == "dms" and task_or_pack:
        result = {"task": task_or_pack, **(full_catalog.get("dms", {}).get(task_or_pack, {}))}
    elif project == "lane" and task_or_pack:
        result = {"pack": task_or_pack, **(full_catalog.get("lane", {}).get(task_or_pack, {}))}
    elif project in ("dms", "lane"):
        result = {"workspace": full_catalog.get("workspace", str(WORKSPACE)), project: full_catalog.get(project, {})}
    else:
        result = dict(full_catalog)

    if not task_or_pack and project is None:
        result["_cache"] = cache_meta
    return result


def warmup_catalog_cache() -> None:
    """Background warmup for faster first page load."""
    try:
        invalidate_catalog_cache()
        get_catalog(refresh=True)
    except Exception:
        pass


def register_batch(
    wf: dict | None,
    project: str,
    task: str | None,
    batch: str,
    *,
    pack: str | None = None,
    stage: str = "returned",
    engineer: str | None = None,
    location: str = "inbox",
) -> dict[str, Any]:
    wf = wf or load_wf()
    root = proj_root(wf, project)

    if project == "dms":
        if not task:
            raise ValueError("dms register-batch 需要 task")
        reg = yaml.safe_load((root / wf["projects"]["dms"]["registry"]).read_text(encoding="utf-8"))
        if task not in reg.get("tasks", {}):
            raise ValueError(f"未知 task: {task}")
        tcfg = reg["tasks"][task]
        if location == "sources":
            if not pack:
                raise ValueError("sources 位置需要 --pack")
            pack_dir = resolve_pack_dir("dms", root, wf, pack)
            src_sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
            batch_dir = pack_dir / tcfg["task_dir"] / src_sub / batch
        else:
            batch_dir = root / "inbox" / task / batch
    elif project == "adas":
        if not task:
            raise ValueError("adas register-batch 需要 task")
        batch_dir = root / "inbox" / task / batch
    else:
        if location == "pack" and pack:
            try:
                path = resolve_pack("lane", root, wf, pack)
                batch_dir = root / path
            except ValueError:
                batch_dir = root / pack
        else:
            batch_dir = root / "inbox" / batch

    if not batch_dir.is_dir():
        raise FileNotFoundError(f"批次目录不存在: {batch_dir}")

    data = {
        "schema": "huaxu-batch-v1",
        "project": project,
        "task": task,
        "pack": pack,
        "batch": batch,
        "stage": stage,
        "engineer": engineer,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    if project == "dms":
        from as_platform.data.batch import count_images, count_label_files, dms_has_images

        data["format"] = "yolo"
        data["counts"] = {
            "images": count_images(batch_dir / "images") + count_images(batch_dir / "images" / "train"),
            "labels": count_label_files(batch_dir / "labels") + count_label_files(batch_dir / "labels" / "train"),
        }
        if not data["counts"]["images"] and dms_has_images(batch_dir):
            data["counts"]["images"] = 1
    elif project == "adas":
        from as_platform.data.batch import count_images, count_label_files, dms_has_images

        data["format"] = "cvat_cuboid"
        data["counts"] = {
            "images": count_images(batch_dir),
            "labels": count_label_files(batch_dir / "labels"),
        }
        if not data["counts"]["images"] and dms_has_images(batch_dir):
            data["counts"]["images"] = count_images(batch_dir / "images")
    else:
        data["format"] = "ufld_archive"
        tg = batch_dir / "list" / "train_gt.txt"
        data["counts"] = {"images": 0, "labels": sum(1 for _ in tg.open()) if tg.is_file() else 0}

    meta_path = write_meta(batch_dir, data)
    invalidate_catalog_cache()
    batch_row = enrich_batch(
        batch_dir,
        project=project,
        task=task,
        pack=pack,
        batch=batch,
        location=location,
    )
    try:
        from as_platform.labeling.batch_index import upsert_batch_dict

        upsert_batch_dict(batch_row)
    except Exception:
        pass
    return {
        "ok": True,
        "meta_path": str(meta_path),
        "batch": batch_row,
    }

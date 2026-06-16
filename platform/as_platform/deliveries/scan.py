"""扫描 inbox / 数据湖目录，与批次台账对齐。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from as_platform.data.core import load_wf, proj_root, register_batch
from as_platform.db.engine import session_scope
from as_platform.db.models import BatchDelivery, BatchIndex, User
from as_platform.deliveries.service import _new_delivery_id, _normalize_task


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dir_mtime_iso(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except OSError:
        return None


def _scan_project_inbox(project: str, wf: dict | None = None) -> list[dict[str, Any]]:
    from as_platform.data.batch import count_images, count_label_files, dms_has_labels

    wf = wf or load_wf()
    root = proj_root(wf, project)
    inbox = root / "inbox"
    if not inbox.is_dir():
        return []

    with session_scope() as db:
        deliveries = {
            (r.project, r.task or "", r.mode or "", r.batch_name): r
            for r in db.query(BatchDelivery).filter(BatchDelivery.project == project).all()
        }
        indexed = {
            (r.task or "", r.batch)
            for r in db.query(BatchIndex).filter(
                BatchIndex.project == project,
                BatchIndex.archived.is_(False),
            ).all()
        }

    items: list[dict[str, Any]] = []
    for task_dir in sorted(inbox.iterdir()):
        if not task_dir.is_dir():
            continue
        for batch_dir in sorted(task_dir.iterdir()):
            if not batch_dir.is_dir():
                continue
            task_name = task_dir.name
            batch_name = batch_dir.name
            img_count = count_images(batch_dir)
            if not img_count and (batch_dir / "images").is_dir():
                img_count = count_images(batch_dir / "images")
            lbl_count = count_label_files(batch_dir / "labels") if (batch_dir / "labels").is_dir() else 0
            has_labels = lbl_count > 0 or dms_has_labels(batch_dir)
            stage_hint = "returned" if has_labels and lbl_count > 0 else "raw_pool"

            key = (project, task_name, "", batch_name)
            delivery = deliveries.get(key)
            in_index = (task_name, batch_name) in indexed

            items.append({
                "project": project,
                "task": task_name,
                "mode": None,
                "batch": batch_name,
                "batch_name": batch_name,
                "path": str(batch_dir),
                "data_path": str(batch_dir),
                "images": img_count,
                "labels": lbl_count,
                "has_labels": has_labels,
                "stage_hint": stage_hint,
                "source_type": "inbox_scan",
                "delivery_id": delivery.id if delivery else None,
                "delivery_status": delivery.status if delivery else None,
                "in_ledger": delivery is not None,
                "in_workbench": in_index,
                "collection_start": delivery.collection_start if delivery else _dir_mtime_iso(batch_dir),
                "collection_end": delivery.collection_end if delivery else None,
                "created_at": delivery.created_at.isoformat() if delivery and delivery.created_at else None,
                "needs_ledger": delivery is None,
                "needs_workbench": not in_index,
            })
    return items


def scan_delivery_sources(*, projects: list[str] | None = None) -> dict[str, Any]:
    """扫描 inbox，返回与台账、工作台对齐状态。"""
    projs = projects or ["dms", "adas", "lane"]
    wf = load_wf()
    items: list[dict[str, Any]] = []
    for p in projs:
        items.extend(_scan_project_inbox(p, wf))
    needs_ledger = sum(1 for i in items if i.get("needs_ledger"))
    needs_workbench = sum(1 for i in items if i.get("needs_workbench"))
    return {
        "items": items,
        "count": len(items),
        "needs_ledger": needs_ledger,
        "needs_workbench": needs_workbench,
        "scanned_at": _utcnow().isoformat(),
    }


def register_scanned_to_ledger(
    items: list[dict[str, Any]],
    user: User,
    *,
    sync_workbench: bool = True,
) -> dict[str, Any]:
    """将扫描结果登记到台账；已在 inbox 的批次直接标为 in_lake 并同步工作台。"""
    created = 0
    updated = 0
    synced = 0
    out_items: list[dict[str, Any]] = []

    for raw in items:
        project = (raw.get("project") or "dms").strip()
        task = _normalize_task(project, raw.get("task"))
        mode = (raw.get("mode") or "").strip() or None
        batch_name = (raw.get("batch_name") or raw.get("batch") or "").strip()
        data_path = (raw.get("data_path") or raw.get("path") or "").strip()
        if not batch_name or not data_path:
            continue
        if not Path(data_path).is_dir():
            continue

        stage_hint = raw.get("stage_hint") or "raw_pool"
        collection_start = (raw.get("collection_start") or "").strip() or _dir_mtime_iso(Path(data_path))
        collection_end = (raw.get("collection_end") or "").strip() or None
        estimated = raw.get("images")
        if estimated is None:
            estimated = raw.get("estimated_count")

        with session_scope() as db:
            rec = (
                db.query(BatchDelivery)
                .filter_by(project=project, task=task, mode=mode, batch_name=batch_name)
                .first()
            )
            if not rec:
                rec = BatchDelivery(
                    id=_new_delivery_id(),
                    project=project,
                    task=task,
                    mode=mode,
                    batch_name=batch_name,
                    source_type=(raw.get("source_type") or "inbox_scan"),
                    collection_start=collection_start,
                    collection_end=collection_end,
                    data_path=data_path,
                    estimated_count=int(estimated) if estimated not in (None, "") else None,
                    status="in_lake",
                    inbox_path=data_path,
                    owner_user_id=user.id,
                    owner_name=user.name,
                    submitted_by_user_id=user.id,
                    submitted_by_name=user.name,
                )
                db.add(rec)
                created += 1
            else:
                if rec.status in ("draft", "rejected", "ingest_failed"):
                    rec.status = "in_lake"
                if not rec.inbox_path:
                    rec.inbox_path = data_path
                if not rec.data_path:
                    rec.data_path = data_path
                if collection_start and not rec.collection_start:
                    rec.collection_start = collection_start
                if estimated not in (None, "") and not rec.estimated_count:
                    rec.estimated_count = int(estimated)
                if not rec.source_type:
                    rec.source_type = "inbox_scan"
                rec.updated_at = _utcnow()
                updated += 1
            db.flush()
            out_items.append(rec.to_dict())

        if sync_workbench and stage_hint in ("raw_pool", "returned"):
            try:
                register_batch(
                    None,
                    project,
                    task,
                    batch_name,
                    stage=stage_hint,
                    location="inbox",
                )
                synced += 1
            except Exception:
                pass

    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "synced_workbench": synced,
        "items": out_items,
    }


def bridge_delivery_to_workbench(delivery_id: str) -> dict[str, Any]:
    """台账 in_lake 后同步到送标工作台索引。"""
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if not rec:
            raise ValueError("送标申请不存在")
        if rec.status != "in_lake":
            raise ValueError(f"当前状态不可同步工作台: {rec.status}")
        project = rec.project
        task = rec.task
        batch_name = rec.batch_name
        inbox_path = rec.inbox_path or rec.data_path

    stage = "raw_pool"
    if inbox_path:
        labels_dir = Path(inbox_path) / "labels"
        if labels_dir.is_dir() and any(labels_dir.iterdir()):
            stage = "returned"

    result = register_batch(None, project, task, batch_name, stage=stage, location="inbox")
    return {"ok": True, "delivery_id": delivery_id, "batch": result.get("batch")}

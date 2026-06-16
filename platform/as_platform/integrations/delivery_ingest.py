"""平台送标申请审批通过后：analyze → promote 入湖。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from as_platform.data.lake import (
    analyze_directory_candidate,
    create_directory_candidate,
    promote_candidate_to_inbox,
)
from as_platform.db.engine import session_scope
from as_platform.db.models import BatchDelivery


def validate_delivery_fields(
    *,
    project: str,
    task: str | None,
    mode: str | None,
    batch_name: str,
    data_path: str,
) -> str | None:
    if not project or not batch_name:
        return "缺少 项目 或 批次名"
    if batch_name == (task or ""):
        return "批次名不能与任务名相同"
    if task in ("dam", "forward") and not (mode or "").strip():
        return f"任务 {task} 须填写 子模式"
    path = (data_path or "").strip()
    if not path:
        return "须填写 数据路径"
    p = Path(path)
    if not p.exists():
        return f"数据路径不存在: {path}"
    if project == "dms" and p.name in ("train", "val", "test") and p.parent.name == "images":
        return f"请填批次根目录（例如 {p.parent.parent}），不要填到 images/train"
    if project == "adas" and task == "det_7cls":
        if "/inbox/det_7cls/" not in str(p).replace("\\", "/"):
            return "ADAS 2D 须落在 adas/inbox/det_7cls/{批次}（project=adas, task=det_7cls）"
    if project == "adas" and task in (None, "", "cuboid_7cls"):
        if "/inbox/cuboid_7cls/" not in str(p).replace("\\", "/"):
            return "ADAS 3D 须落在 adas/inbox/cuboid_7cls/{批次}（project=adas, task=cuboid_7cls）"
    if project == "dms" and task == "adas":
        if "/inbox/adas/" not in str(p).replace("\\", "/"):
            return "旧版 ADAS 2D 路径 dms/inbox/adas/{批次}；新数据请用 adas/inbox/det_7cls/"
    return None


def ingest_from_directory(
    *,
    project: str,
    task: str | None,
    mode: str | None,
    batch_name: str,
    data_path: str,
    delivery_id: str | None = None,
) -> dict[str, Any]:
    """目录分析并 promote 到 inbox。"""
    err = validate_delivery_fields(
        project=project,
        task=task,
        mode=mode,
        batch_name=batch_name,
        data_path=data_path,
    )
    if err:
        raise ValueError(err)

    src = Path(data_path.strip())
    task_eff = task if project in ("dms", "adas") else None
    cand = create_directory_candidate(
        project=project,
        task=task_eff,
        mode=mode or None,
        source_dir=src,
        source_type="platform_delivery",
        external_id=delivery_id,
    )
    cid = cand["id"]
    analyze_directory_candidate(cid, src)
    promo = promote_candidate_to_inbox(cid, batch=batch_name, mode=mode or None)
    return {
        "ok": True,
        "candidate_id": cid,
        "inbox_path": promo.get("inbox_path") or "",
        "batch": promo.get("batch") or batch_name,
    }


def run_delivery_ingest(delivery_id: str) -> dict[str, Any]:
    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if not rec:
            raise ValueError(f"送标申请不存在: {delivery_id}")
        rec.status = "ingesting"
        rec.error_message = None
        db.flush()
        project = rec.project
        task = rec.task
        mode = rec.mode
        batch_name = rec.batch_name
        data_path = rec.data_path

    try:
        result = ingest_from_directory(
            project=project,
            task=task,
            mode=mode,
            batch_name=batch_name,
            data_path=data_path,
            delivery_id=delivery_id,
        )
    except Exception as e:
        from as_platform.deliveries.service import mark_delivery_ingest_failed

        mark_delivery_ingest_failed(delivery_id, None, str(e))
        raise

    with session_scope() as db:
        rec = db.get(BatchDelivery, delivery_id)
        if rec:
            rec.status = "in_lake"
            rec.candidate_id = result.get("candidate_id")
            rec.inbox_path = result.get("inbox_path")
            rec.error_message = None
            db.flush()

    try:
        from as_platform.deliveries.scan import bridge_delivery_to_workbench

        bridge_delivery_to_workbench(delivery_id)
    except Exception:
        pass

    return result

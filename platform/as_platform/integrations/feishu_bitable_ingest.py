"""飞书多维表格「待落盘」→ analyze → promote（Phase B，FEISHU_BITABLE_AUTO_INGEST）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from as_platform.config import FEISHU_BITABLE_FIELDS
from as_platform.data.lake import (
    analyze_directory_candidate,
    create_feishu_directory_candidate,
    promote_candidate_to_inbox,
)
from as_platform.db.engine import session_scope
from as_platform.db.models import DatasetCandidate, FeishuBitableLink
from as_platform.integrations.feishu_bitable import is_bitable_configured, list_all_records, update_record
from as_platform.integrations.feishu_bitable_sync import batch_key


def _validate_row(flat: dict[str, str]) -> str | None:
    project = flat.get("project") or ""
    task = flat.get("task") or ""
    batch_name = flat.get("batch_name") or ""
    mode = flat.get("mode") or ""
    if not project or not batch_name:
        return "缺少 项目 或 批次名"
    if batch_name == task:
        return "批次名不能与任务名相同"
    if task in ("dam", "forward") and not mode:
        return f"任务 {task} 须填写 子模式"
    data_path = (flat.get("data_path") or "").strip()
    if not data_path:
        return "待落盘须填写 数据路径（内网 NAS）"
    if not Path(data_path).exists():
        return f"数据路径不存在: {data_path}"
    return None


def _already_ingested(flat: dict[str, str], delivery_id: str) -> bool:
    cid = (flat.get("candidate_id") or "").strip()
    if cid:
        with session_scope() as db:
            rec = db.get(DatasetCandidate, cid)
            if rec and rec.status in ("promoted", "analyzed") and rec.inbox_path:
                return True
    if delivery_id:
        with session_scope() as db:
            link = db.query(FeishuBitableLink).filter_by(delivery_id=delivery_id).first()
            if link and link.inbox_path:
                return True
    return False


def process_pending_ingest() -> dict[str, Any]:
    if not is_bitable_configured():
        return {"ok": False, "message": "未配置多维表格", "processed": 0}

    records = list_all_records()
    processed = 0
    skipped = 0
    errors: list[str] = []

    for rec in records:
        record_id = rec.get("record_id")
        flat = rec.get("flat") or {}
        if not record_id:
            continue
        if flat.get("status") != "待落盘":
            continue

        delivery_id = flat.get("delivery_id") or ""
        if _already_ingested(flat, delivery_id):
            skipped += 1
            continue

        err = _validate_row(flat)
        if err:
            try:
                update_record(record_id, {"status": "落盘失败", "error_message": err})
            except Exception as e:
                errors.append(f"{record_id}: {e}")
            continue

        try:
            update_record(record_id, {"status": "分析中", "error_message": ""})
        except Exception:
            pass

        project = flat.get("project") or "dms"
        task = flat.get("task") or None
        mode = flat.get("mode") or None
        batch_name = flat.get("batch_name") or ""
        src = Path((flat.get("data_path") or "").strip())

        try:
            cand = create_feishu_directory_candidate(
                project=project,
                task=task if project == "dms" else None,
                mode=mode or None,
                source_dir=src,
                external_id=delivery_id or None,
                feishu_record_id=record_id,
            )
            cid = cand["id"]
            analyze_directory_candidate(cid, src)
            promo = promote_candidate_to_inbox(cid, batch=batch_name, mode=mode or None)
            inbox_path = promo.get("inbox_path") or ""

            update_record(
                record_id,
                {
                    "status": "待送标",
                    "candidate_id": cid,
                    "inbox_path": inbox_path,
                    "error_message": "",
                    "record_id": record_id,
                },
            )

            key = batch_key(
                project,
                task if project == "dms" else None,
                mode,
                promo.get("batch") or batch_name,
            )
            with session_scope() as db:
                link = db.query(FeishuBitableLink).filter_by(batch_key=key).first()
                if not link:
                    link = FeishuBitableLink(
                        batch_key=key,
                        record_id=record_id,
                        delivery_id=delivery_id or None,
                        project=project,
                        task=task,
                        mode=mode,
                        batch=promo.get("batch") or batch_name,
                    )
                    db.add(link)
                link.record_id = record_id
                link.delivery_id = delivery_id or link.delivery_id
                link.inbox_path = inbox_path
                db.flush()

            processed += 1
        except Exception as e:
            msg = str(e)
            errors.append(f"{record_id}: {msg}")
            try:
                update_record(record_id, {"status": "落盘失败", "error_message": msg[:500]})
            except Exception:
                pass

    return {
        "ok": True,
        "processed": processed,
        "skipped": skipped,
        "errors": errors[:20],
        "status_field": FEISHU_BITABLE_FIELDS.get("status"),
    }

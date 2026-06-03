"""HSAP 批次 → 飞书多维表格回写（内网 Phase A）。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from as_platform.config import FEISHU_STATUS_FROM_STAGE, FRONTEND_URL
from as_platform.data.core import get_pending_report
from as_platform.db.engine import session_scope
from as_platform.db.models import FeishuBitableLink
from as_platform.integrations.feishu_bitable import is_bitable_configured, list_all_records, update_record
from as_platform.labeling.progress import campaign_progress_summary
from as_platform.labeling.service import list_labeling_batches


def batch_key(project: str, task: str | None, mode: str | None, batch: str, location: str = "inbox") -> str:
    return f"{location}:{project}:{task or ''}:{mode or ''}:{batch}"


def _collect_hsap_batches() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        for row in list_labeling_batches().get("items") or []:
            key = batch_key(
                row.get("project") or "dms",
                row.get("task"),
                row.get("mode"),
                row.get("batch") or "",
                row.get("location") or "inbox",
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(row)
    except Exception:
        pass

    try:
        report = get_pending_report()
        for row in report.get("batches") or []:
            if row.get("stage") == "ingested":
                continue
            key = batch_key(
                row.get("project") or "dms",
                row.get("task"),
                row.get("mode"),
                row.get("batch") or "",
                row.get("location") or "inbox",
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(row)
    except Exception:
        pass

    return items


def _find_batch_for_record(
    flat: dict[str, str],
    hsap_batches: list[dict[str, Any]],
    links_by_delivery: dict[str, FeishuBitableLink],
) -> dict[str, Any] | None:
    did = (flat.get("delivery_id") or "").strip()
    if did and did in links_by_delivery:
        key = links_by_delivery[did].batch_key
        for b in hsap_batches:
            if batch_key(
                b.get("project") or "dms",
                b.get("task"),
                b.get("mode"),
                b.get("batch") or "",
                b.get("location") or "inbox",
            ) == key:
                return b
    for b in hsap_batches:
        if _match_record_to_batch(flat, b):
            return b
    return None


def _match_record_to_batch(flat: dict[str, str], b: dict[str, Any]) -> bool:
    if flat.get("project") and flat.get("project") != (b.get("project") or ""):
        return False
    if flat.get("task") and flat.get("task") != (b.get("task") or ""):
        return False
    bm = flat.get("batch_name") or ""
    if bm and bm != (b.get("batch") or ""):
        return False
    fm = flat.get("mode") or ""
    if fm and fm != (b.get("mode") or ""):
        return False
    if not bm and not fm:
        return False
    return True


def _progress_for_batch(b: dict[str, Any]) -> tuple[str, str | None]:
    cid = b.get("campaign_id")
    if not cid:
        return "", None
    try:
        prog = campaign_progress_summary(cid)
        return f"{prog.get('completed_tasks', 0)}/{prog.get('total_tasks', 0)}", cid
    except Exception:
        return "", cid


def _hsap_link(b: dict[str, Any], campaign_id: str | None) -> dict[str, str]:
    base = FRONTEND_URL.rstrip("/")
    if campaign_id:
        path = f"/labeling/campaigns/{campaign_id}/annotate"
        label = "进入标注"
    else:
        path = "/labeling"
        label = "送标工作台"
    url = f"{base}{path}"
    batch = b.get("batch") or ""
    return {"text": f"{label} · {batch}", "link": url}


def sync_hsap_to_bitable() -> dict[str, Any]:
    if not is_bitable_configured():
        return {"ok": False, "message": "飞书多维表格未配置", "updated": 0}

    hsap_batches = _collect_hsap_batches()
    records = list_all_records()
    updated = 0
    matched_keys: set[str] = set()
    errors: list[str] = []

    with session_scope() as db:
        links = db.query(FeishuBitableLink).all()
    links_by_delivery = {lnk.delivery_id: lnk for lnk in links if lnk.delivery_id}

    now = datetime.now(timezone.utc)

    for rec in records:
        record_id = rec.get("record_id")
        flat = rec.get("flat") or {}
        if not record_id:
            continue

        hit = _find_batch_for_record(flat, hsap_batches, links_by_delivery)
        if not hit:
            continue

        key = batch_key(
            hit.get("project") or "dms",
            hit.get("task"),
            hit.get("mode"),
            hit.get("batch") or "",
            hit.get("location") or "inbox",
        )
        matched_keys.add(key)

        stage = hit.get("stage") or "raw_pool"
        feishu_status = FEISHU_STATUS_FROM_STAGE.get(stage)
        progress, cid = _progress_for_batch(hit)
        path = hit.get("path") or ""

        payload: dict[str, Any] = {
            "record_id": record_id,
            "inbox_path": path,
            "progress": progress or None,
            "campaign_id": cid,
            "hsap_link": _hsap_link(hit, cid),
            "last_sync": now,
        }
        if feishu_status:
            payload["status"] = feishu_status

        try:
            update_record(record_id, payload)
            updated += 1
            with session_scope() as db:
                link = db.query(FeishuBitableLink).filter_by(batch_key=key).first()
                if not link:
                    link = FeishuBitableLink(
                        batch_key=key,
                        record_id=record_id,
                        project=hit.get("project") or "dms",
                        task=hit.get("task"),
                        mode=hit.get("mode"),
                        batch=hit.get("batch") or "",
                    )
                    db.add(link)
                link.record_id = record_id
                link.delivery_id = flat.get("delivery_id") or link.delivery_id
                link.campaign_id = cid
                link.inbox_path = path
                link.last_sync_at = now
                db.flush()
        except Exception as e:
            errors.append(f"{record_id}: {e}")

    return {
        "ok": True,
        "updated": updated,
        "hsap_batches": len(hsap_batches),
        "bitable_rows": len(records),
        "matched": len(matched_keys),
        "errors": errors[:20],
    }


def backfill_hints() -> dict[str, Any]:
    """返回尚未在飞书表匹配到的 HSAP 批次（需人工补录行）。"""
    hsap_batches = _collect_hsap_batches()
    records = list_all_records() if is_bitable_configured() else []
    unmatched: list[dict[str, Any]] = []

    for b in hsap_batches:
        found = False
        for rec in records:
            if _match_record_to_batch(rec.get("flat") or {}, b):
                found = True
                break
        if not found:
            unmatched.append(
                {
                    "project": b.get("project"),
                    "task": b.get("task"),
                    "mode": b.get("mode"),
                    "batch": b.get("batch"),
                    "stage": b.get("stage"),
                    "path": b.get("path"),
                    "suggested_batch_name": b.get("batch"),
                }
            )

    return {"unmatched_count": len(unmatched), "items": unmatched[:100]}

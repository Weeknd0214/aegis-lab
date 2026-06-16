"""Campaign 与 pending 批次合并列表。"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from as_platform.config import WORKSPACE
from as_platform.data.core import get_pending_report, load_wf
from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign, LabelingExportJob, User
from as_platform.jobs.queue import enqueue_job, get_job
from as_platform.labeling.annotate import resolve_campaign_batch_dir, _iter_batch_images
from as_platform.labeling.batch_stage import (
    on_labeling_export_job_succeeded,
    update_campaign_batch_meta_stage,
)
from as_platform.labeling.stage import effective_stage, matches_stage_filter
from as_platform.labeling.scope import (
    enrich_batch_labels,
    format_scope_key,
    load_dms_registry,
    load_labeling_registry,
)


def _campaign_id(project: str, task: str, mode: str | None, batch: str, location: str) -> str:
    sk = format_scope_key(project, task, mode)
    raw = f"{sk}:{batch}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _parse_scope_key(scope_key: str) -> tuple[str, str, str | None]:
    parts = scope_key.split(":")
    if parts[0] == "lane":
        return "lane", parts[1] if len(parts) > 1 else "lane_v1", None
    if parts[0] == "adas":
        return "adas", parts[1] if len(parts) > 1 else "cuboid_7cls", None
    if len(parts) >= 3:
        return "dms", parts[1], parts[2]
    if len(parts) == 2:
        return "dms", parts[1], None
    return "dms", parts[-1], None


def _registry_fallback_batches(wf: dict, reg: dict) -> list[dict[str, Any]]:
    """labeling.registry 中有配置但 pending 未扫到的批次（如空 inbox）。"""
    from pathlib import Path

    from as_platform.data.batch import enrich_batch
    from as_platform.data.core import proj_root

    profiles = load_labeling_registry().get("profiles") or {}
    rows: list[dict[str, Any]] = []
    dms_root = proj_root(wf, "dms")
    for _pk, prof in profiles.items():
        scope_key = prof.get("scope_key") or ""
        project, task, mode = _parse_scope_key(scope_key)
        if project != "dms":
            continue
        batch = mode or task
        batch_dir = None
        if mode:
            try:
                import sys

                scripts = WORKSPACE / "datasets" / "dms" / "scripts"
                if str(scripts) not in sys.path:
                    sys.path.insert(0, str(scripts))
                from task_registry import inbox_dir, resolve_task_id

                task_r, mode_r = resolve_task_id(task, mode)
                batch_dir = inbox_dir(dms_root, task_r, mode_r, reg)
            except Exception:
                batch_dir = dms_root / "inbox" / task / mode
        else:
            batch_dir = dms_root / "inbox" / task / batch
        if not isinstance(batch_dir, Path) or not batch_dir.is_dir():
            row = {
                "project": project,
                "task": task,
                "mode": mode,
                "batch": batch,
                "stage": "raw_pool",
                "location": "inbox",
                "path": str(batch_dir) if batch_dir else "",
                "counts": {"images": 0, "labels": 0},
                "registry_only": True,
            }
        else:
            row = enrich_batch(
                batch_dir,
                project=project,
                task=task,
                pack=None,
                batch=batch,
                location="inbox",
            )
            row["mode"] = mode
        row["scope_key"] = scope_key
        rows.append(row)
    return rows


def list_labeling_batches(
    *,
    stage: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    wf = load_wf()
    report = get_pending_report(wf)
    reg = load_dms_registry()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_stages = ("raw_pool", "out_for_labeling", "returned", "labeling_submitted", "in_review", "review_approved", "review_rejected")

    def _append(b: dict[str, Any]) -> None:
        if b.get("registry_only"):
            return
        raw_stage = b.get("stage")
        eff = effective_stage(raw_stage)
        if stage and not matches_stage_filter(raw_stage, stage):
            return
        if eff not in allowed_stages and raw_stage not in allowed_stages:
            return
        row = enrich_batch_labels(b, reg)
        row["stage"] = eff or raw_stage
        cid = _campaign_id(
            row["project"], row.get("task") or "", row.get("mode"), row["batch"], row.get("location") or "inbox"
        )
        key = f"{cid}"
        if key in seen:
            return
        seen.add(key)
        with session_scope() as db:
            camp = db.get(LabelingCampaign, cid)
            status = camp.status if camp else "not_opened"
            if camp:
                row["assigned_to_user_id"] = camp.assigned_to_user_id
                row["assigned_to_name"] = camp.assigned_to_name
        row["campaign_id"] = cid
        row["campaign_status"] = status
        if camp and status in ("in_progress", "labeling_submitted"):
            try:
                from as_platform.labeling.progress import campaign_progress_summary

                row.update(campaign_progress_summary(cid))
            except Exception:
                row.update({"total_tasks": 0, "completed_tasks": 0, "assigned_tasks": 0})
        items.append(row)

    for b in report.get("batches", []):
        _append(b)

    for b in _registry_fallback_batches(wf, reg):
        _append(b)

    total = len(items)
    page = items[max(0, offset) : max(0, offset) + max(1, limit)]
    return {
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "updated_at": report.get("updated_at"),
    }


def open_campaign(
    *,
    project: str,
    task: str,
    batch: str,
    mode: str | None = None,
    pack: str | None = None,
    location: str = "inbox",
    annotation_types: list[str] | None = None,
) -> dict[str, Any]:
    cid = _campaign_id(project, task, mode, batch, location)
    now = datetime.now(timezone.utc)
    ann_types = annotation_types or _resolve_default_annotation_types(project, task, mode)

    from as_platform.labeling.cvat_client import get_cvat_client
    from as_platform.labeling.cvat_config import build_cvat_labels

    cvat = get_cvat_client()
    if not cvat.ping():
        raise ValueError("CVAT 标注引擎不可用，请执行: docker compose -f docker-compose.yml -f docker-compose.cvat.yml up -d")

    cvat_labels = build_cvat_labels(project, task, mode, ann_types)
    cvat_task = cvat.create_task(name=cid, labels=cvat_labels)
    cvat_task_id = cvat_task.id
    cvat_job_url = cvat_task.job_url

    with session_scope() as db:
        camp = db.get(LabelingCampaign, cid)
        if not camp:
            camp = LabelingCampaign(
                id=cid,
                project=project,
                task=task,
                mode=mode,
                batch=batch,
                pack=pack,
                location=location,
                status="in_progress",
                cvat_task_id=cvat_task_id,
                cvat_job_url=cvat_job_url,
                annotation_types=ann_types,
                created_at=now,
                updated_at=now,
            )
            db.add(camp)
        else:
            camp.status = "in_progress"
            camp.updated_at = now
            if cvat_task_id and not camp.cvat_task_id:
                camp.cvat_task_id = cvat_task_id
                camp.cvat_job_url = cvat_job_url
            if ann_types and not camp.annotation_types:
                camp.annotation_types = ann_types
        db.flush()
        out = camp.to_dict()

        # CVAT 图片上传（异步，不阻塞）
        try:
            batch_dir = resolve_campaign_batch_dir(camp)
            images = _iter_batch_images(batch_dir)
            if images:
                import threading
                cvat_uploader = _cvat_upload_thread(cvat_task_id, images)
                threading.Thread(target=cvat_uploader, daemon=True).start()
        except Exception:
            pass

        update_campaign_batch_meta_stage(camp, "out_for_labeling")
    reg = load_dms_registry() if project == "dms" else None
    row = enrich_batch_labels(out, reg)
    row["stage"] = "out_for_labeling"
    return row


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return None
        row = camp.to_dict()
    reg = load_dms_registry() if row.get("project") == "dms" else None
    return enrich_batch_labels(row, reg)


def _export_job_id() -> str:
    return f"lej-{uuid.uuid4().hex[:16]}"


def _record_export_job(campaign_id: str, action: str, job: dict[str, Any]) -> dict[str, Any]:
    ej_id = _export_job_id()
    job_id = job.get("id")
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        ej = LabelingExportJob(
            id=ej_id,
            campaign_id=campaign_id,
            action=action,
            job_id=job_id,
            status=job.get("status") or "queued",
            created_at=now,
        )
        db.add(ej)
    out = get_export_job(ej_id)
    return out or {"id": ej_id, "campaign_id": campaign_id, "action": action, "job_id": job_id}


def _sync_export_job_from_queue(ej: LabelingExportJob) -> None:
    if not ej.job_id:
        return
    job = get_job(ej.job_id)
    if not job:
        return
    ej.status = job.get("status") or ej.status
    if job.get("finished_at"):
        try:
            ej.finished_at = datetime.fromisoformat(str(job["finished_at"]).replace("Z", "+00:00"))
        except Exception:
            pass
    if job.get("result") is not None:
        ej.result_json = json.dumps(job.get("result"), ensure_ascii=False)
    if ej.action == "labeling_export" and ej.status in ("succeeded", "completed"):
        on_labeling_export_job_succeeded(
            {"action": "labeling_export", "params": {"campaign_id": ej.campaign_id}}
        )


def get_export_job(export_job_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        ej = db.get(LabelingExportJob, export_job_id)
        if not ej:
            return None
        _sync_export_job_from_queue(ej)
        db.flush()
        return ej.to_dict()


def list_campaign_export_jobs(campaign_id: str, *, limit: int = 30) -> dict[str, Any]:
    with session_scope() as db:
        rows = (
            db.query(LabelingExportJob)
            .filter_by(campaign_id=campaign_id)
            .filter(LabelingExportJob.action != "labeling_ml_predict")
            .order_by(LabelingExportJob.created_at.desc())
            .limit(limit)
            .all()
        )
        for ej in rows:
            _sync_export_job_from_queue(ej)
        db.flush()
        items = [ej.to_dict() for ej in rows]
    return {"items": items, "campaign_id": campaign_id}


def list_labeling_assignees() -> dict[str, Any]:
    """可指派用户：从飞书通讯录同步组织全员，供分配下拉选择。"""
    from as_platform.auth.feishu import is_feishu_configured, sync_feishu_users_to_db

    role_codes = ("labeler", "internal_labeler", "vendor_labeler", "engineer", "admin")
    sync_meta: dict[str, Any] = {"feishu_configured": is_feishu_configured()}
    if sync_meta["feishu_configured"]:
        from as_platform.config import FEISHU_APP_ID
        sync_meta["contact_scope_url"] = (
            f"https://open.feishu.cn/app/{FEISHU_APP_ID}/auth"
            "?q=contact:contact:readonly_as_app,contact:department.organize:readonly,contact:contact.base:readonly"
            "&op_from=openapi&token_type=tenant"
        )
        sync_meta["publish_url"] = f"https://open.feishu.cn/app/{FEISHU_APP_ID}/appPublish"
    with session_scope() as db:
        if is_feishu_configured():
            try:
                sync_result = sync_feishu_users_to_db(db)
                sync_meta.update(sync_result)
            except Exception as exc:
                sync_meta["error"] = str(exc)
        users = (
            db.query(User)
            .filter(User.is_active.is_(True), User.feishu_open_id.isnot(None))
            .order_by(User.name)
            .all()
        )
        if not users:
            users = (
                db.query(User)
                .filter(User.is_active.is_(True))
                .order_by(User.name)
                .all()
            )
            users = [
                u for u in users
                if {r.code for r in (u.roles or [])}.intersection(role_codes)
            ]
            sync_meta["fallback"] = "local_roles"
        items = []
        for u in users:
            items.append({
                "id": u.id,
                "name": u.name or f"user-{u.id}",
                "avatar_url": u.avatar_url,
                "roles": sorted({r.code for r in (u.roles or [])}),
                "department_names": u.feishu_department_ids(),
                "feishu_open_id": u.feishu_open_id,
            })
    return {"items": items, "sync": sync_meta}


def _find_batch_for_campaign_id(campaign_id: str) -> dict[str, Any] | None:
    """由确定性 campaign_id 反查 pending / registry 批次行。"""
    wf = load_wf()
    reg = load_dms_registry()
    candidates: list[dict[str, Any]] = []
    report = get_pending_report(wf)
    candidates.extend(report.get("batches") or [])
    candidates.extend(_registry_fallback_batches(wf, reg))
    for b in candidates:
        cid = _campaign_id(
            b.get("project") or "dms",
            b.get("task") or "",
            b.get("mode"),
            b.get("batch") or "",
            b.get("location") or "inbox",
        )
        if cid == campaign_id:
            return b
    return None


def ensure_campaign_record(campaign_id: str) -> None:
    """提交/导出前保证 DB 中有 LabelingCampaign（未点「进入标注」时自动创建）。"""
    with session_scope() as db:
        if db.get(LabelingCampaign, campaign_id):
            return
    batch = _find_batch_for_campaign_id(campaign_id)
    if not batch:
        raise FileNotFoundError("campaign not found")
    if batch.get("registry_only"):
        raise ValueError("该条目为任务模板占位，无真实 inbox 批次目录，请先送标入湖或从「进入标注」开启真实批次")
    open_campaign(
        project=batch.get("project") or "dms",
        task=batch.get("task") or "",
        batch=batch["batch"],
        mode=batch.get("mode"),
        pack=batch.get("pack"),
        location=batch.get("location") or "inbox",
    )


def assign_campaign(campaign_id: str, user_id: int | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        if user_id is None:
            camp.assigned_to_user_id = None
            camp.assigned_to_name = None
        else:
            user = db.get(User, user_id)
            if not user:
                raise ValueError(f"用户不存在: {user_id}")
            camp.assigned_to_user_id = user_id
            camp.assigned_to_name = user.name
        camp.updated_at = now
        db.flush()
        out = camp.to_dict()
    reg = load_dms_registry() if out.get("project") == "dms" else None
    return enrich_batch_labels(out, reg)


def submit_campaign(campaign_id: str) -> dict[str, Any]:
    ensure_campaign_record(campaign_id)
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        camp.status = "in_review"
        camp.updated_at = now
        db.flush()
        out = camp.to_dict()
        update_campaign_batch_meta_stage(camp, "in_review")
    reg = load_dms_registry() if out.get("project") == "dms" else None
    row = enrich_batch_labels(out, reg)
    row["stage"] = "in_review"
    return row


def trigger_labeling_export(campaign_id: str) -> dict[str, Any]:
    row = get_campaign(campaign_id)
    if not row:
        raise FileNotFoundError("campaign not found")
    job = enqueue_job(
        "labeling_export",
        {
            "campaign_id": campaign_id,
            "export_default": row.get("export_default"),
            "scope_key": row.get("scope_key"),
            "batch": row.get("batch"),
        },
        async_run=True,
    )
    ej = _record_export_job(campaign_id, "labeling_export", job)
    return {"ok": True, "job": job, "export_job": ej, "export_default": row.get("export_default")}


def get_batch_export_stats(campaign_id: str) -> dict[str, Any]:
    from as_platform.labeling.annotate import resolve_campaign_batch_dir
    from as_platform.data.promote.validate.adas_cuboid import validate_adas_cuboid_batch
    from as_platform.labeling.batch_stage import batch_has_cuboid_labels, batch_has_yolo_labels

    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        project = camp.project
        batch_dir = resolve_campaign_batch_dir(camp)
    if project == "adas":
        _errors, warnings, stats = validate_adas_cuboid_batch(batch_dir, allow_partial_3d=True)
        calib = (batch_dir / "calib").is_dir() and bool(list((batch_dir / "calib").glob("*.yaml")))
        return {
            "project": "adas",
            "campaign_id": campaign_id,
            "pack_default": "adas_moon3d_v1",
            "quaternion_files": stats.get("quaternion_files", 0),
            "fit_ok_ratio": stats.get("fit_ok_ratio", 0),
            "missing_calib": not calib,
            "stats": stats,
            "warnings": warnings,
        }
    return {
        "project": project,
        "campaign_id": campaign_id,
        "has_yolo": batch_has_yolo_labels(batch_dir),
        "has_cuboid": batch_has_cuboid_labels(batch_dir),
    }


def trigger_cuboid_fit(campaign_id: str) -> dict[str, Any]:
    row = get_campaign(campaign_id)
    if not row:
        raise FileNotFoundError("campaign not found")
    if row.get("project") != "adas":
        raise ValueError("cuboid_fit_3d 仅适用于 ADAS")
    job = enqueue_job("cuboid_fit_3d", {"campaign_id": campaign_id}, async_run=True)
    return {"ok": True, "job": job}


# ═══════════════════════════════════════════════════════
# CVAT 集成辅助
# ═══════════════════════════════════════════════════════

def _resolve_default_annotation_types(project: str, task: str | None, mode: str | None) -> list[str]:
    """根据 project 推断默认标注类型。"""
    from as_platform.labeling.cvat_config import resolve_annotation_types
    return resolve_annotation_types(project, task, mode)


def _cvat_upload_thread(cvat_task_id: int, image_paths: list):
    """在线程中上传图片到 CVAT。"""
    def _run():
        try:
            from as_platform.labeling.cvat_client import get_cvat_client
            cvat = get_cvat_client()
            cvat.upload_images(cvat_task_id, image_paths)
        except Exception:
            pass
    return _run


def sync_cvat_annotations(campaign_id: str) -> dict[str, Any]:
    """从 CVAT Job 拉取标注，写入 HSAP 数据湖 labels/ls_annotations。"""
    from datetime import datetime, timezone

    from as_platform.labeling.annotate import _annotations_dir, _iter_batch_images, _task_id_for_image
    from as_platform.labeling.cvat_client import get_cvat_client
    from as_platform.labeling.format_converter import (
        cvat_job_shapes_to_yolo_lines,
        cvat_shapes_to_export_regions,
        group_cvat_job_shapes_by_frame,
    )

    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        if not camp.cvat_task_id:
            raise ValueError("该 campaign 未关联 CVAT Task")

        cvat = get_cvat_client()
        task = cvat.get_task(camp.cvat_task_id)
        if not task.job_id:
            raise ValueError("CVAT Job 尚未就绪，请等待图片上传完成")

        job_id = task.job_id
        job_ann = cvat.get_job_annotations(job_id)
        meta = cvat.get_job_data_meta(job_id)
        label_map = cvat.get_job_label_map(job_id)
        frames = meta.get("frames") or []
        shapes_by_frame = group_cvat_job_shapes_by_frame(job_ann)

        batch_dir = resolve_campaign_batch_dir(camp)
        images = _iter_batch_images(batch_dir)
        name_to_path = {p.name: p for p in images}
        ann_dir = _annotations_dir(batch_dir)
        synced_at = datetime.now(timezone.utc).isoformat()

        from as_platform.labeling.scope import load_dms_registry

        reg = load_dms_registry() if camp.project == "dms" else None
        class_map = _build_class_map(camp, reg)

        saved_count = 0
        shape_count = 0
        for frame_idx, shapes in shapes_by_frame.items():
            if frame_idx >= len(frames):
                continue
            frame_name = frames[frame_idx].get("name") or f"frame_{frame_idx}"
            img_path = name_to_path.get(Path(frame_name).name)
            if not img_path:
                continue

            task_id = _task_id_for_image(img_path, batch_dir)
            fw = int(frames[frame_idx].get("width") or 1920)
            fh = int(frames[frame_idx].get("height") or 1080)
            result_items = cvat_shapes_to_export_regions(shapes, label_map, fw, fh)
            shape_count += len(result_items)

            payload: dict[str, Any] = {
                "task_id": task_id,
                "result": result_items,
                "source": "cvat",
                "synced_at": synced_at,
                "cvat_job_id": job_id,
                "image": frame_name,
            }
            ann_file = ann_dir / f"{task_id}.json"
            ann_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            saved_count += 1

            # DMS / ADAS 2D：额外写 YOLO txt 供训练导出
            if camp.project in ("dms", "adas") and class_map:
                yolo_lines = cvat_job_shapes_to_yolo_lines(shapes, label_map, class_map, fw, fh)
                if yolo_lines:
                    yolo_dir = batch_dir / "labels" / "yolo"
                    yolo_dir.mkdir(parents=True, exist_ok=True)
                    stem = Path(frame_name).stem
                    (yolo_dir / f"{stem}.txt").write_text("\n".join(yolo_lines) + "\n", encoding="utf-8")

        return {
            "ok": True,
            "saved": saved_count,
            "shapes": shape_count,
            "campaign_id": campaign_id,
            "cvat_job_id": job_id,
        }


def _build_class_map(camp, reg: dict | None) -> dict[str, int]:
    """从 DMS registry 构建 class_name → class_id 映射。"""
    if reg:
        tasks = reg.get("tasks") or {}
        tcfg = tasks.get(camp.task) or {}
        names = tcfg.get("names") or []
        if isinstance(names, list):
            return {n: i for i, n in enumerate(names)}
    return {}


def get_cvat_status(campaign_id: str) -> dict[str, Any]:
    """查询 CVAT 侧 Task 状态。"""
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        if not camp.cvat_task_id:
            return {"cvat_available": False, "campaign_id": campaign_id}

        from as_platform.labeling.cvat_client import get_cvat_client
        cvat = get_cvat_client()
        try:
            task = cvat.get_task(camp.cvat_task_id)
            return {
                "cvat_available": True,
                "campaign_id": campaign_id,
                "cvat_task_id": camp.cvat_task_id,
                "cvat_job_url": task.job_url or camp.cvat_job_url,
                "cvat_status": task.status,
            }
        except Exception as e:
            return {"cvat_available": False, "campaign_id": campaign_id, "error": str(e)}

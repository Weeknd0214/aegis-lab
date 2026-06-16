"""同步 inbox/sources 批次 batch.meta.yaml 的 stage，与 Campaign 状态一致。"""
from __future__ import annotations

import json
from pathlib import Path

from as_platform.data.batch import read_meta, write_meta
from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign
from as_platform.labeling.annotate import resolve_campaign_batch_dir


def batch_has_yolo_labels(batch_dir: Path) -> bool:
    """批次是否已有导出的 YOLO txt（labels/train 或 labels 根目录）。"""
    for sub in ("labels/train", "labels"):
        d = batch_dir / sub
        if d.is_dir() and any(d.glob("*.txt")):
            return True
    return False


def batch_has_cuboid_labels(batch_dir: Path) -> bool:
    """批次是否已有导出的 ADAS quaternion_json（含非空 detections）。"""
    qdir = batch_dir / "labels" / "quaternion_json"
    if not qdir.is_dir():
        return False
    for p in qdir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dets = data.get("detections") or []
        if isinstance(dets, list) and len(dets) > 0:
            return True
    return False


def batch_has_lane_labels(batch_dir: Path) -> bool:
    """批次是否已有 UFLD mask 清单（list/train_gt.txt + annotations/*.png）。"""
    list_path = batch_dir / "list" / "train_gt.txt"
    if not list_path.is_file():
        return False
    ann_dir = batch_dir / "annotations"
    if not ann_dir.is_dir():
        return False
    return any(ann_dir.rglob("*.png"))


def _batch_has_export_labels(project: str, batch_dir: Path) -> bool:
    if project == "lane":
        return batch_has_lane_labels(batch_dir)
    if project == "adas":
        return batch_has_cuboid_labels(batch_dir)
    return batch_has_yolo_labels(batch_dir)


def update_campaign_batch_meta_stage(camp: LabelingCampaign, stage: str) -> bool:
    try:
        batch_dir = resolve_campaign_batch_dir(camp)
    except Exception:
        return False
    if not batch_dir.is_dir():
        return False
    meta = read_meta(batch_dir) or {}
    meta["stage"] = stage
    meta.setdefault("project", camp.project)
    meta.setdefault("task", camp.task)
    meta.setdefault("batch", camp.batch)
    meta.setdefault("location", camp.location or "inbox")
    if camp.mode:
        meta.setdefault("mode", camp.mode)
    write_meta(batch_dir, meta)
    try:
        from as_platform.labeling.batch_index import sync_index_stage

        sync_index_stage(camp.id, stage)
    except Exception:
        pass
    return True


def update_campaign_batch_meta_stage_by_id(campaign_id: str, stage: str) -> bool:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return False
    return update_campaign_batch_meta_stage(camp, stage)


def _advance_campaign_stage(campaign_id: str, stage: str) -> None:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, str(campaign_id))
        if not camp:
            return
        camp.status = stage
        db.flush()
        update_campaign_batch_meta_stage(camp, stage)


def _batch_has_calib(batch_dir: Path) -> bool:
    calib = batch_dir / "calib"
    return calib.is_dir() and bool(list(calib.glob("*.yaml")) + list(calib.glob("*.yml")))


def on_labeling_export_job_succeeded(job: dict) -> None:
    """导出 Job 成功且批次已有训练标签时进入 returned（待 build）。"""
    if job.get("action") != "labeling_export":
        return
    params = job.get("params") or {}
    cid = params.get("campaign_id")
    if not cid:
        return
    with session_scope() as db:
        camp = db.get(LabelingCampaign, str(cid))
        if not camp:
            return
        try:
            batch_dir = resolve_campaign_batch_dir(camp)
        except Exception:
            return
        project = camp.project or "dms"
    if _batch_has_export_labels(project, batch_dir):
        _advance_campaign_stage(str(cid), "returned")
    if project == "adas" and _batch_has_calib(batch_dir):
        from as_platform.jobs.queue import enqueue_job

        enqueue_job(
            "cuboid_fit_3d",
            {"campaign_id": str(cid)},
            async_run=True,
        )


def on_build_job_succeeded(job: dict) -> None:
    """build Job 成功后将批次晋升 ingested。"""
    action = job.get("action")
    if action not in ("build_dms", "build_adas", "build_lane"):
        return
    params = job.get("params") or {}
    batch = params.get("batch")
    if not batch:
        return
    project = params.get("project")
    if not project:
        if action == "build_adas":
            project = "adas"
        elif action == "build_lane":
            project = "lane"
        else:
            project = "dms"
    task = params.get("task")
    with session_scope() as db:
        q = db.query(LabelingCampaign).filter(LabelingCampaign.batch == str(batch))
        if task:
            q = q.filter(LabelingCampaign.task == str(task))
        if project:
            q = q.filter(LabelingCampaign.project == str(project))
        camp = q.order_by(LabelingCampaign.created_at.desc()).first()
        if not camp:
            return
        camp.status = "ingested"
        db.flush()
        update_campaign_batch_meta_stage(camp, "ingested")

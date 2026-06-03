"""同步 inbox/sources 批次 batch.meta.yaml 的 stage，与 Campaign 状态一致。"""
from __future__ import annotations

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


def batch_has_lane_labels(batch_dir: Path) -> bool:
    """批次是否已有 UFLD mask 清单（list/train_gt.txt + annotations/*.png）。"""
    list_path = batch_dir / "list" / "train_gt.txt"
    if not list_path.is_file():
        return False
    ann_dir = batch_dir / "annotations"
    if not ann_dir.is_dir():
        return False
    return any(ann_dir.rglob("*.png"))


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
    return True


def update_campaign_batch_meta_stage_by_id(campaign_id: str, stage: str) -> bool:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return False
    return update_campaign_batch_meta_stage(camp, stage)


def on_labeling_export_job_succeeded(job: dict) -> None:
    """导出 Job 成功且批次已有训练标签时进入 returned（待入库）。"""
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
    has_labels = (
        batch_has_lane_labels(batch_dir)
        if camp.project == "lane"
        else batch_has_yolo_labels(batch_dir)
    )
    if has_labels:
        update_campaign_batch_meta_stage_by_id(str(cid), "returned")

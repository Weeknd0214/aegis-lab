"""标注画布：批次目录、LS 配置 XML、任务列表、标注 JSON、媒体文件。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from as_platform.config import WORKSPACE
from as_platform.data.batch import IMG_EXTS
from as_platform.data.core import load_wf, proj_root, resolve_pack_dir
from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign, User
from as_platform.labeling.scope import (
    enrich_batch_labels,
    labeling_profile_key,
    load_dms_registry,
    load_labeling_registry,
)

ANNOTATIONS_DIRNAME = "ls_annotations"


def _label_config_dir(project: str) -> Path:
    return WORKSPACE / "datasets" / project / "configs" / "label_studio"

_FALLBACK_XML = """<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="object"/>
  </RectangleLabels>
</View>"""


def _load_campaign(campaign_id: str) -> LabelingCampaign | None:
    with session_scope() as db:
        return db.get(LabelingCampaign, campaign_id)


def resolve_editor_xml(project: str, task: str, mode: str | None) -> str:
    reg = load_dms_registry() if project == "dms" else None
    pk = labeling_profile_key(project, task or "lane_v1", mode, reg)
    prof = (load_labeling_registry().get("profiles") or {}).get(pk) or {}
    default_tpl = "dam_15cls.xml" if project == "dms" else "lane_ufld_mask.xml"
    template = prof.get("editor_template") or default_tpl
    path = _label_config_dir(project) / template
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return _FALLBACK_XML


def resolve_campaign_batch_dir(camp: LabelingCampaign) -> Path:
    wf = load_wf()
    root = proj_root(wf, camp.project)
    if camp.project == "dms":
        reg = yaml.safe_load((root / wf["projects"]["dms"]["registry"]).read_text(encoding="utf-8"))
        tcfg = reg["tasks"][camp.task]
        if camp.location == "sources":
            if not camp.pack:
                raise ValueError("sources 批次需要 pack")
            pack_dir = resolve_pack_dir("dms", root, wf, camp.pack)
            src_sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
            return (pack_dir / tcfg["task_dir"] / src_sub / camp.batch).resolve()
        if tcfg.get("type") == "multi" and camp.mode:
            from as_platform.labeling.scope import _dms_registry_api

            get_mode_config, resolve_task_id, _ = _dms_registry_api()
            task_r, mode_r = resolve_task_id(camp.task, camp.mode)
            mcfg = get_mode_config(task_r, mode_r, reg)
            inbox_rel = mcfg.get("inbox")
            if inbox_rel:
                return (root / inbox_rel).resolve()
        mode = camp.mode
        if mode:
            return (root / "inbox" / camp.task / mode / camp.batch).resolve()
        return (root / "inbox" / camp.task / camp.batch).resolve()
    if camp.location == "pack" and camp.pack:
        try:
            from as_platform.data.core import resolve_pack

            rel = resolve_pack("lane", root, wf, camp.pack)
            return (root / rel).resolve()
        except ValueError:
            return (root / camp.pack).resolve()
    return (root / "inbox" / camp.batch).resolve()


def _iter_batch_images(batch_dir: Path) -> list[Path]:
    if not batch_dir.is_dir():
        return []
    candidates: list[Path] = []
    search_roots = [
        batch_dir / "images",
        batch_dir / "images" / "train",
        batch_dir,
    ]
    seen: set[str] = set()
    for root in search_roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in IMG_EXTS:
                continue
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(p.resolve())
    return candidates


def _task_id_for_image(image_path: Path, batch_dir: Path) -> str:
    try:
        rel = image_path.relative_to(batch_dir)
        stem = rel.as_posix()
    except ValueError:
        stem = image_path.stem
    return hashlib.sha256(stem.encode()).hexdigest()[:16]


def _annotations_dir(batch_dir: Path) -> Path:
    d = batch_dir / "labels" / ANNOTATIONS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def sync_campaign_config_xml(camp: LabelingCampaign) -> str:
    """始终与 labeling.registry + 模板文件对齐，避免 campaign 卡在旧 fallback XML。"""
    xml = resolve_editor_xml(camp.project, camp.task, camp.mode)
    if camp.config_xml != xml:
        camp.config_xml = xml
    return xml


def campaign_bootstrap(campaign_id: str) -> dict[str, Any]:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        sync_campaign_config_xml(camp)
        reg = load_dms_registry() if camp.project == "dms" else None
        row = enrich_batch_labels(camp.to_dict(), reg)
        row["config_xml"] = camp.config_xml
        try:
            batch_dir = resolve_campaign_batch_dir(camp)
            row["batch_path"] = str(batch_dir)
            row["image_count"] = len(_iter_batch_images(batch_dir))
        except Exception as e:
            row["batch_path"] = None
            row["image_count"] = 0
            row["batch_error"] = str(e)
    return row


def campaign_tasks(
    campaign_id: str,
    *,
    offset: int = 0,
    limit: int = 50,
    user: User | None = None,
    assignee: str | None = None,
) -> dict[str, Any]:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
    images = _iter_batch_images(batch_dir)
    from as_platform.labeling.progress import get_assigned_task_ids, user_is_coordinator

    filter_ids: set[str] | None = None
    if assignee == "me" and user:
        filter_ids = get_assigned_task_ids(campaign_id, user.id)
        if not filter_ids and not user_is_coordinator(user):
            return {
                "tasks": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "hint": "暂无分配给您的任务，请联系协调员在送标工作台均分任务",
            }

    if filter_ids is not None:
        filtered = [img for img in images if _task_id_for_image(img, batch_dir) in filter_ids]
        images = filtered

    total = len(images)
    slice_imgs = images[offset : offset + limit]
    tasks: list[dict[str, Any]] = []
    for img in slice_imgs:
        tid = _task_id_for_image(img, batch_dir)
        try:
            rel = img.relative_to(batch_dir).as_posix()
        except ValueError:
            rel = img.name
        media_path = quote(rel, safe="/")
        tasks.append(
            {
                "id": tid,
                "data": {
                    "image": f"/api/v1/labeling/media/{campaign_id}/{media_path}",
                },
                "meta": {"filename": img.name, "relative_path": rel},
            }
        )
    out: dict[str, Any] = {"tasks": tasks, "total": total, "offset": offset, "limit": limit}
    if filter_ids is not None and user and assignee == "me":
        out["my_assigned"] = len(filter_ids)
    return out


def resolve_media_file(campaign_id: str, rel_path: str) -> Path:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
    clean = Path(rel_path)
    if clean.is_absolute() or ".." in clean.parts:
        raise PermissionError("invalid path")
    target = (batch_dir / clean).resolve()
    if not target.is_file() or not target.is_relative_to(batch_dir.resolve()):
        raise FileNotFoundError("media not found")
    return target


def get_annotation(campaign_id: str, task_id: str) -> dict[str, Any]:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
    path = _annotations_dir(batch_dir) / f"{task_id}.json"
    if not path.is_file():
        return {"task_id": task_id, "result": None, "annotations": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def save_annotation(
    campaign_id: str,
    task_id: str,
    payload: dict[str, Any],
    *,
    user: User | None = None,
) -> dict[str, Any]:
    from as_platform.labeling.progress import assert_can_save_task, mark_task_completed

    if user:
        assert_can_save_task(campaign_id, task_id, user)
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
    path = _annotations_dir(batch_dir) / f"{task_id}.json"
    now = datetime.now(timezone.utc).isoformat()
    extra: dict[str, Any] = {}
    if user:
        extra["completed_by_user_id"] = user.id
        extra["completed_at"] = now
    out = {"task_id": task_id, **payload, **extra}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if user and _annotation_has_result(path):
        mark_task_completed(campaign_id, task_id, user.id)
    return {"ok": True, "path": str(path)}


def _annotation_has_result(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    result = data.get("result")
    if result is None:
        return False
    if isinstance(result, list):
        return len(result) > 0
    if isinstance(result, dict):
        return len(result) > 0
    return bool(result)

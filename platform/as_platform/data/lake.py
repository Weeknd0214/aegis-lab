"""Upload candidate lifecycle for data-lake ingestion."""
from __future__ import annotations

import json
import shutil
import tarfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

import yaml

from as_platform.config import MANIFESTS
from as_platform.data.batch import META_FILENAME, dms_has_images, enrich_batch, write_meta
from as_platform.data.catalog_cache import invalidate_catalog_cache
from as_platform.data.core import load_wf, proj_root
from as_platform.data.ingest import inspect_uploaded_dataset
from as_platform.db.engine import session_scope
from as_platform.db.models import DatasetCandidate

LAKE_ROOT = MANIFESTS / "lake"
UPLOAD_ROOT = LAKE_ROOT / "uploads"
STAGING_ROOT = LAKE_ROOT / "staging"
REPORT_ROOT = LAKE_ROOT / "reports"


def _new_candidate_id() -> str:
    return f"cand-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


def _candidate_dirs(candidate_id: str) -> tuple[Path, Path, Path]:
    upload_dir = UPLOAD_ROOT / candidate_id
    staging_dir = STAGING_ROOT / candidate_id
    report_file = REPORT_ROOT / f"{candidate_id}.json"
    return upload_dir, staging_dir, report_file


def create_uploaded_candidate(
    *,
    project: str,
    task: str | None,
    mode: str | None = None,
    original_name: str,
    upload_size_bytes: int,
    submitted_by_name: str | None,
    submitted_by_user_id: int | None,
) -> dict:
    candidate_id = _new_candidate_id()
    upload_dir, _, _ = _candidate_dirs(candidate_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / original_name
    with session_scope() as db:
        rec = DatasetCandidate(
            id=candidate_id,
            project=project,
            task=task,
            mode=mode,
            status="uploaded",
            source_type="upload",
            original_name=original_name,
            upload_path=str(upload_path),
            upload_size_bytes=upload_size_bytes,
            submitted_by_name=submitted_by_name,
            submitted_by_user_id=submitted_by_user_id,
        )
        db.add(rec)
        db.flush()
        return rec.to_dict()


def write_candidate_upload(candidate_id: str, stream: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if not rec:
            raise ValueError(f"candidate not found: {candidate_id}")
        path = Path(rec.upload_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
        rec.upload_size_bytes = path.stat().st_size
        db.flush()
        return str(path)


def list_candidates(*, offset: int = 0, limit: int = 20) -> dict[str, Any]:
    with session_scope() as db:
        q = db.query(DatasetCandidate).order_by(DatasetCandidate.created_at.desc())
        total = q.count()
        rows = q.offset(max(0, offset)).limit(max(1, limit)).all()
        return {
            "items": [r.to_dict() for r in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }


def get_candidate(candidate_id: str) -> dict | None:
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        return rec.to_dict() if rec else None


def link_candidate_analysis_job(candidate_id: str, job_id: str) -> None:
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if not rec:
            raise ValueError(f"candidate not found: {candidate_id}")
        rec.analysis_job_id = job_id
        db.flush()


def _extract_to_staging(upload_path: Path, staging_dir: Path) -> Path:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    name = upload_path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(upload_path, "r") as zf:
            zf.extractall(staging_dir)
    elif name.endswith(".tar") or name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(upload_path, "r:*") as tf:
            tf.extractall(staging_dir)
    else:
        raise ValueError(f"unsupported archive format: {upload_path.name}")

    subdirs = [p for p in staging_dir.iterdir() if p.is_dir()]
    files = [p for p in staging_dir.iterdir() if p.is_file()]
    if len(subdirs) == 1 and not files:
        return subdirs[0]
    return staging_dir


def analyze_uploaded_candidate(candidate_id: str) -> dict:
    upload_dir, staging_dir, report_file = _candidate_dirs(candidate_id)
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if not rec:
            raise ValueError(f"candidate not found: {candidate_id}")
        rec.status = "analyzing"
        rec.error_message = None
        db.flush()
        project = rec.project
        task = rec.task
        upload_path = Path(rec.upload_path)

    if not upload_path.is_file():
        with session_scope() as db:
            rec = db.get(DatasetCandidate, candidate_id)
            if rec:
                rec.status = "failed"
                rec.error_message = f"upload file missing: {upload_path}"
        raise FileNotFoundError(f"upload file missing: {upload_path}")

    try:
        dataset_root = _extract_to_staging(upload_path, staging_dir)
        if project == "dms":
            dataset_root = _ensure_dms_inbox_layout(dataset_root)
        normalized = inspect_uploaded_dataset(project, task, dataset_root)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(normalized.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        with session_scope() as db:
            rec = db.get(DatasetCandidate, candidate_id)
            if not rec:
                raise ValueError(f"candidate not found during finalize: {candidate_id}")
            rec.status = "analyzed"
            rec.analyzed_source_path = str(dataset_root)
            rec.format_id = normalized.format_id
            rec.set_split_counts(normalized.split_counts)
            rec.set_quality(normalized.to_dict())
            rec.error_message = None
            db.flush()
        invalidate_catalog_cache()
        return normalized.to_dict()
    except Exception as e:
        with session_scope() as db:
            rec = db.get(DatasetCandidate, candidate_id)
            if rec:
                rec.status = "failed"
                rec.error_message = str(e)
                db.flush()
        raise


_SPLIT_DIR_NAMES = frozenset({"train", "val", "test"})
_STRUCTURE_DIR_NAMES = frozenset({"images", "labels", "annotations"})


def _dataset_root_from_dir(source_dir: Path) -> Path:
    """解析批次根目录；勿把 images/ 或 train/ 误剥成更深层导致丢失 images 层。"""
    if not source_dir.is_dir():
        raise FileNotFoundError(f"not a directory: {source_dir}")
    subdirs = [p for p in source_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    files = [p for p in source_dir.iterdir() if p.is_file()]
    if len(subdirs) == 1 and not files:
        only = subdirs[0]
        if only.name in _SPLIT_DIR_NAMES or only.name in _STRUCTURE_DIR_NAMES:
            return source_dir
        return only
    return source_dir


def _ensure_dms_inbox_layout(root: Path) -> Path:
    """将 dataset/train 布局规范为 …/images/train；已是批次根或 images/ 目录则不改动。"""
    if not root.is_dir():
        return root
    from as_platform.data.batch import count_images, dms_has_images

    if dms_has_images(root):
        return root
    if root.name == "images" and count_images(root / "train") > 0:
        return root
    if count_images(root) > 0 and not any(
        (root / sub).is_dir() for sub in ("images", "train", "labels")
    ):
        images_dir = root / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        dest_train = images_dir / "train"
        dest_train.mkdir(parents=True, exist_ok=True)
        for item in list(root.iterdir()):
            if item.is_file() and item.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                shutil.move(str(item), str(dest_train / item.name))
        return root

    train_dir = root / "train"
    if not train_dir.is_dir() or count_images(train_dir) == 0:
        return root
    images_dir = root / "images"
    if images_dir.is_dir() and count_images(images_dir / "train") > 0:
        return root
    images_dir.mkdir(parents=True, exist_ok=True)
    dest_train = images_dir / "train"
    if dest_train.exists():
        shutil.rmtree(dest_train, ignore_errors=True)
    shutil.move(str(train_dir), str(dest_train))
    return root


def analyze_directory_candidate(candidate_id: str, source_dir: Path | None = None) -> dict:
    """分析目录型数据源（飞书 data_path / NAS），无需 zip 上传。"""
    upload_dir, staging_dir, report_file = _candidate_dirs(candidate_id)
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if not rec:
            raise ValueError(f"candidate not found: {candidate_id}")
        rec.status = "analyzing"
        rec.error_message = None
        db.flush()
        project = rec.project
        task = rec.task
        root = source_dir or Path(rec.upload_path)

    if not root.is_dir():
        msg = f"source directory missing: {root}"
        with session_scope() as db:
            rec = db.get(DatasetCandidate, candidate_id)
            if rec:
                rec.status = "failed"
                rec.error_message = msg
        raise FileNotFoundError(msg)

    try:
        dataset_root = _dataset_root_from_dir(root)
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        shutil.copytree(dataset_root, staging_dir / "dataset", dirs_exist_ok=True)
        analyzed_root = staging_dir / "dataset"
        if project == "dms":
            analyzed_root = _ensure_dms_inbox_layout(analyzed_root)
        normalized = inspect_uploaded_dataset(project, task, analyzed_root)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(normalized.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        with session_scope() as db:
            rec = db.get(DatasetCandidate, candidate_id)
            if not rec:
                raise ValueError(f"candidate not found during finalize: {candidate_id}")
            rec.status = "analyzed"
            rec.analyzed_source_path = str(analyzed_root)
            rec.format_id = normalized.format_id
            rec.set_split_counts(normalized.split_counts)
            rec.set_quality(normalized.to_dict())
            rec.error_message = None
            db.flush()
        invalidate_catalog_cache()
        return normalized.to_dict()
    except Exception as e:
        with session_scope() as db:
            rec = db.get(DatasetCandidate, candidate_id)
            if rec:
                rec.status = "failed"
                rec.error_message = str(e)
                db.flush()
        raise


def create_directory_candidate(
    *,
    project: str,
    task: str | None,
    mode: str | None,
    source_dir: Path,
    source_type: str = "platform_delivery",
    external_id: str | None = None,
    feishu_record_id: str | None = None,
) -> dict:
    """为外部目录（平台送标申请 / 飞书台账）创建入湖候选。"""
    candidate_id = _new_candidate_id()
    upload_dir, _, _ = _candidate_dirs(candidate_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as db:
        rec = DatasetCandidate(
            id=candidate_id,
            project=project,
            task=task,
            mode=mode,
            status="uploaded",
            source_type=source_type,
            original_name=source_dir.name,
            upload_path=str(source_dir.resolve()),
            upload_size_bytes=0,
            external_id=external_id,
            feishu_record_id=feishu_record_id,
        )
        db.add(rec)
        db.flush()
        return rec.to_dict()


def create_feishu_directory_candidate(
    *,
    project: str,
    task: str | None,
    mode: str | None,
    source_dir: Path,
    external_id: str | None = None,
    feishu_record_id: str | None = None,
) -> dict:
    """为飞书台账行创建候选并指向 NAS/本地目录。"""
    return create_directory_candidate(
        project=project,
        task=task,
        mode=mode,
        source_dir=source_dir,
        source_type="feishu_bitable",
        external_id=external_id,
        feishu_record_id=feishu_record_id,
    )


def _copy_tree_into(dest: Path, src: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                _copy_tree_into(target, item)
            else:
                shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _resolve_dms_inbox_dest(root: Path, reg: dict, task: str, mode: str | None, batch_name: str) -> Path:
    import sys

    from as_platform.config import WORKSPACE

    scripts = WORKSPACE / "datasets" / "dms" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from task_registry import inbox_dir, resolve_task_id

    task_r, mode_r = resolve_task_id(task, mode)
    tcfg = (reg.get("tasks") or {}).get(task_r) or {}
    ib = inbox_dir(root, task_r, mode_r, reg)
    if tcfg.get("type") == "multi" and mode_r:
        if dms_has_images(ib) or (ib / META_FILENAME).is_file():
            return ib
        return ib / batch_name
    return ib / batch_name


def promote_candidate_to_inbox(
    candidate_id: str,
    *,
    batch: str | None = None,
    mode: str | None = None,
) -> dict:
    """将 analyzed 候选数据复制到 inbox，并登记 batch.meta。"""
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if not rec:
            raise ValueError(f"candidate not found: {candidate_id}")
        if rec.status not in ("analyzed",):
            raise ValueError(f"candidate 状态须为 analyzed，当前: {rec.status}")
        if not rec.analyzed_source_path:
            raise ValueError("缺少 analyzed_source_path，请先完成分析")
        project = rec.project
        task = rec.task
        eff_mode = mode or rec.mode
        src = Path(rec.analyzed_source_path)
        cand_format_id = rec.format_id

    if not src.is_dir():
        raise FileNotFoundError(f"分析目录不存在: {src}")

    wf = load_wf()
    root = proj_root(wf, project)
    batch_name = batch or src.name or candidate_id.split("-", 1)[-1]

    if project == "dms":
        if not task:
            raise ValueError("DMS 晋级需要 task")
        reg_path = root / wf["projects"]["dms"]["registry"]
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        tcfg = (reg.get("tasks") or {}).get(task) or {}
        if tcfg.get("type") == "multi" and not eff_mode:
            raise ValueError(f"任务 {task} 为 multi，须指定 mode（如 batch_0516）")
        dest = _resolve_dms_inbox_dest(root, reg, task, eff_mode, batch_name)
        reg_batch = eff_mode or batch_name
    else:
        dest = root / "inbox" / batch_name
        reg_batch = batch_name

    if dest.exists() and any(dest.iterdir()):
        _copy_tree_into(dest, src)
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

    row = enrich_batch(
        dest,
        project=project,
        task=task if project == "dms" else None,
        pack=None,
        batch=reg_batch,
        location="inbox",
    )
    fmt = row.get("format", "yolo")
    if cand_format_id == "dms_inbox_raw":
        fmt = "inbox_raw"
    meta_payload = {
        "schema": "huaxu-batch-v1",
        "project": project,
        "task": task,
        "batch": reg_batch,
        "stage": "raw_pool",
        "location": "inbox",
        "format": fmt,
        "counts": row.get("counts", {}),
    }
    if eff_mode:
        meta_payload["mode"] = eff_mode
    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if rec:
            if rec.external_id:
                meta_payload["external_id"] = rec.external_id
            if rec.feishu_record_id:
                meta_payload["feishu_record_id"] = rec.feishu_record_id
            if rec.source_type and rec.source_type != "upload":
                meta_payload["source_type"] = rec.source_type
    write_meta(dest, meta_payload)
    meta = {**row, "stage": "raw_pool"}

    with session_scope() as db:
        rec = db.get(DatasetCandidate, candidate_id)
        if rec:
            rec.status = "promoted"
            rec.inbox_path = str(dest)
            rec.promoted_batch = reg_batch
            if eff_mode:
                rec.mode = eff_mode
            db.flush()

    invalidate_catalog_cache()
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "inbox_path": str(dest),
        "batch": meta.get("batch", reg_batch),
        "stage": meta.get("stage"),
        "counts": meta.get("counts"),
    }

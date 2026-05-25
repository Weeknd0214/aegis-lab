"""Upload candidate lifecycle for data-lake ingestion."""
from __future__ import annotations

import json
import shutil
import tarfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from as_platform.config import MANIFESTS
from as_platform.data.catalog_cache import invalidate_catalog_cache
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


def list_candidates(limit: int = 100) -> list[dict]:
    with session_scope() as db:
        rows = (
            db.query(DatasetCandidate)
            .order_by(DatasetCandidate.created_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]


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

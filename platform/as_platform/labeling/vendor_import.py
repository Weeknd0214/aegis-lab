"""第三方标注回传包（ZIP）导入到 Campaign 批次目录。"""
from __future__ import annotations

import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from as_platform.labeling.annotate import ANNOTATIONS_DIRNAME, resolve_campaign_batch_dir
from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign, LabelingCampaignAccess


def grant_campaign_access(
    db,
    *,
    campaign_id: str,
    principal_type: str = "role",
    principal_id: str = "vendor_labeler",
    access_role: str = "vendor",
) -> dict:
    row = (
        db.query(LabelingCampaignAccess)
        .filter_by(campaign_id=campaign_id, principal_type=principal_type, principal_id=principal_id)
        .first()
    )
    if not row:
        row = LabelingCampaignAccess(
            campaign_id=campaign_id,
            principal_type=principal_type,
            principal_id=principal_id,
            access_role=access_role,
        )
        db.add(row)
        db.flush()
    return row.to_dict()


def import_vendor_zip(campaign_id: str, raw: bytes) -> dict[str, Any]:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
        grant_campaign_access(db, campaign_id=campaign_id)

    batch_dir.mkdir(parents=True, exist_ok=True)
    images_dir = batch_dir / "images"
    labels_dir = batch_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    img_count = 0
    label_count = 0
    manifest: dict[str, Any] = {}

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").lstrip("/")
            lower = name.lower()
            if lower == "manifest.json":
                manifest = json.loads(zf.read(info))
                continue
            data = zf.read(info)
            base = Path(name).name
            if not base:
                continue
            if "/images/" in lower or lower.startswith("images/"):
                dest = images_dir / base
                dest.write_bytes(data)
                img_count += 1
            elif "/labels/" in lower or lower.startswith("labels/"):
                dest = labels_dir / base
                dest.write_bytes(data)
                label_count += 1
            elif base.endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
                (images_dir / base).write_bytes(data)
                img_count += 1
            elif base.endswith((".txt", ".json")):
                (labels_dir / base).write_bytes(data)
                label_count += 1

    ann_dir = batch_dir / ANNOTATIONS_DIRNAME
    ann_dir.mkdir(parents=True, exist_ok=True)

    return {
        "ok": True,
        "campaign_id": campaign_id,
        "batch_path": str(batch_dir),
        "images_imported": img_count,
        "labels_imported": label_count,
        "manifest": manifest,
    }


def list_registry_profiles() -> dict[str, Any]:
    from as_platform.labeling.scope import load_labeling_registry

    reg = load_labeling_registry()
    profiles = reg.get("profiles") or {}
    items = []
    for key, prof in profiles.items():
        items.append(
            {
                "profile_key": key,
                "editor_template": prof.get("editor_template"),
                "export_default": prof.get("export_default"),
                "ml_adapter": prof.get("ml_adapter"),
                "type": prof.get("type"),
            }
        )
    return {"profiles": items, "version": reg.get("version")}

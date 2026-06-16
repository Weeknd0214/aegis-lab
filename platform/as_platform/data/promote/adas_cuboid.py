"""ADAS cuboid MOON-3D pack promote adapter."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from as_platform.data.batch import read_meta, write_meta
from as_platform.data.promote.base import PackPromoteAdapter, PromoteContext, PromoteResult
from as_platform.data.promote.manifest import refresh_adas_lists
from as_platform.data.promote.validate.adas_cuboid import validate_adas_cuboid_batch
from as_platform.labeling.class_map import build_class_map, load_adas_class_names, normalize_detection_class

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _link_or_copy(src: Path, dst: Path, *, copy: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if copy:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return
    try:
        os.link(src, dst)
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def _sync_tree(src: Path, dst: Path, *, copy: bool = False) -> int:
    count = 0
    if not src.is_dir():
        return 0
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        target = dst / rel
        if not target.exists():
            _link_or_copy(p, target, copy=copy)
            count += 1
    return count


def _normalize_quaternion_json(dest_batch: Path) -> int:
    qdir = dest_batch / "labels" / "quaternion_json"
    if not qdir.is_dir():
        return 0
    cmap = build_class_map(load_adas_class_names())
    names = load_adas_class_names()
    updated = 0
    for p in qdir.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        dets = []
        for det in data.get("detections") or []:
            dets.append(normalize_detection_class(det, cmap))
        data["detections"] = dets
        data["text_prompts"] = names
        data["num_detections"] = len(dets)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
    return updated


class AdasCuboidPromoteAdapter(PackPromoteAdapter):
    project = "adas"

    def validate(self, ctx: PromoteContext) -> list[str]:
        if ctx.skip_validate:
            return []
        errors, warnings, _stats = validate_adas_cuboid_batch(
            ctx.batch_dir,
            allow_partial_3d=ctx.allow_partial_3d,
        )
        ctx.extra.setdefault("validate_warnings", warnings)
        return errors

    def promote(self, ctx: PromoteContext) -> PromoteResult:
        warnings = list(ctx.extra.get("validate_warnings") or [])
        qdir = ctx.batch_dir / "labels" / "quaternion_json"
        if not qdir.is_dir() or not any(qdir.glob("*.json")):
            return PromoteResult(
                ok=False,
                project=ctx.project,
                task=ctx.task,
                batch=ctx.batch,
                pack=ctx.pack,
                warnings=["missing quaternion_json export"],
            )

        pack_dir = ctx.project_root / "packs" / ctx.pack
        dest = pack_dir / "sources" / ctx.batch
        if ctx.dry_run:
            return PromoteResult(
                ok=True,
                project=ctx.project,
                task=ctx.task,
                batch=ctx.batch,
                pack=ctx.pack,
                dest_path=str(dest),
                detail={"dry_run": True},
            )

        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        copied = 0
        for sub in ("images", "calib", "labels"):
            src_sub = ctx.batch_dir / sub
            if src_sub.is_dir():
                copied += _sync_tree(src_sub, dest / sub)

        normalized = _normalize_quaternion_json(dest)

        meta = read_meta(ctx.batch_dir) or {}
        meta.update({
            "stage": "ingested",
            "project": ctx.project,
            "task": ctx.task,
            "batch": ctx.batch,
            "pack": ctx.pack,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": 2,
        })
        write_meta(dest, meta)
        write_meta(ctx.batch_dir, meta)

        manifest = refresh_adas_lists(pack=ctx.pack)
        img_count = sum(1 for _ in (dest / "images").rglob("*") if _.suffix.lower() in IMG_EXTS) if (dest / "images").is_dir() else 0

        return PromoteResult(
            ok=True,
            project=ctx.project,
            task=ctx.task,
            batch=ctx.batch,
            pack=ctx.pack,
            dest_path=str(dest),
            images=img_count,
            labels=normalized,
            manifest_paths=[manifest.get("train_list", ""), manifest.get("val_list", "")],
            warnings=warnings,
            detail={"copied_files": copied, "normalized_json": normalized, **manifest},
        )

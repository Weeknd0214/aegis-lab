"""标注质检 — 逐张审核标注质量（Good/Fine/Bad 评分 + PIL 优化渲染）。"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from as_platform.data.batch import IMG_EXTS
from as_platform.db.engine import session_scope
from as_platform.db.models import Base

IMAGE_EXTS = tuple(ext.lower() for ext in IMG_EXTS)

# ── PIL font cache ──
_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except Exception:
            try:
                _font_cache[size] = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", size)
            except Exception:
                _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


# ── YOLO bbox utils ──

def _parse_yolo_line(line: str) -> dict[str, Any] | None:
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        return {"class_id": int(float(parts[0])), "bbox": tuple(map(float, parts[1:5]))}
    except Exception:
        return None


def _bbox_to_xyxy(bbox: tuple[float, ...], w: int, h: int) -> tuple[int, int, int, int]:
    cx, cy, bw, bh = bbox[:4]
    x1 = int((cx - bw / 2) * w)
    y1 = int((cy - bh / 2) * h)
    x2 = int((cx + bw / 2) * w)
    y2 = int((cy + bh / 2) * h)
    return max(0, x1), max(0, y1), min(w, x2), min(h, y2)


def _parse_labels(label_path: Path) -> list[dict[str, Any]]:
    if not label_path or not label_path.is_file():
        return []
    results = []
    for line in label_path.read_text().strip().splitlines():
        ann = _parse_yolo_line(line)
        if ann and ann["bbox"][2] > 0 and ann["bbox"][3] > 0:
            results.append(ann)
    return results


def _class_names_for_campaign(camp) -> dict[int, str]:
    """campaign task → class_id → name。"""
    import yaml
    from as_platform.data.core import load_wf, proj_root

    if not camp or camp.project != "dms":
        return {}
    wf = load_wf()
    root = proj_root(wf, "dms")
    reg = yaml.safe_load((root / wf["projects"]["dms"]["registry"]).read_text(encoding="utf-8")) or {}
    tcfg = (reg.get("tasks") or {}).get(camp.task) or {}
    if camp.mode and tcfg.get("type") == "multi":
        mcfg = (tcfg.get("modes") or {}).get(camp.mode) or {}
        names = mcfg.get("names")
    else:
        names = tcfg.get("names")
    if isinstance(names, list):
        return {i: str(n) for i, n in enumerate(names)}
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    return {}


def _name_to_class_id(name: str, class_names: dict[int, str]) -> int:
    rev = {v.lower(): k for k, v in class_names.items()}
    return rev.get(name.lower(), 0)


def _resolve_yolo_label_path(batch_dir: Path, img_path: Path) -> Path | None:
    stem = img_path.stem
    for rel in (
        f"labels/{stem}.txt",
        f"labels/train/{stem}.txt",
        f"labels/val/{stem}.txt",
        f"labels/yolo/{stem}.txt",
    ):
        p = batch_dir / rel
        if p.is_file():
            return p
    return None


def _parse_ls_annotations(path: Path, class_names: dict[int, str]) -> list[dict[str, Any]]:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[dict[str, Any]] = []
    for item in data.get("result") or []:
        if item.get("type") not in ("rectanglelabels", "rectangle"):
            continue
        val = item.get("value") or {}
        w_pct = float(val.get("width") or 0)
        h_pct = float(val.get("height") or 0)
        if w_pct <= 0 or h_pct <= 0:
            continue
        x_pct = float(val.get("x") or 0)
        y_pct = float(val.get("y") or 0)
        labels = val.get("rectanglelabels") or val.get("labels") or []
        label = labels[0] if labels else "unknown"
        cid = _name_to_class_id(str(label), class_names)
        cx = (x_pct + w_pct / 2) / 100.0
        cy = (y_pct + h_pct / 2) / 100.0
        out.append({"class_id": cid, "bbox": (cx, cy, w_pct / 100.0, h_pct / 100.0)})
    return out


def _load_image_annotations(
    batch_dir: Path,
    img_path: Path,
    class_names: dict[int, str],
) -> list[dict[str, Any]]:
    yolo = _resolve_yolo_label_path(batch_dir, img_path)
    if yolo:
        anns = _parse_labels(yolo)
        if anns:
            return anns
    from as_platform.labeling.annotate import _task_id_for_image

    ann_json = batch_dir / "labels" / "ls_annotations" / f"{_task_id_for_image(img_path, batch_dir)}.json"
    if ann_json.is_file():
        return _parse_ls_annotations(ann_json, class_names)
    return []


def _image_has_labels(batch_dir: Path, img_path: Path, class_names: dict[int, str]) -> bool:
    return bool(_load_image_annotations(batch_dir, img_path, class_names))


def _list_review_images(batch_dir: Path) -> list[Path]:
    from as_platform.labeling.annotate import _iter_batch_images

    return list(_iter_batch_images(batch_dir))

# ── Optimized overlay render ──

PALETTE = [(220, 20, 60), (30, 144, 255), (50, 205, 50), (255, 165, 0), (186, 85, 211), (0, 206, 209)]


def render_review_overlay(
    image_path: Path,
    batch_dir: Path,
    class_names: dict[int, str],
    *,
    max_size: int = 800,
    quality: int = 85,
) -> bytes:
    """PIL optimized: single pass resize + draw, no copy. Returns JPEG bytes."""
    with Image.open(image_path) as im:
        if im.mode != "RGB":
            im = im.convert("RGB")
        # Resize first for faster drawing
        if max_size and max(im.size) > max_size:
            im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        w, h = im.size
        draw = ImageDraw.Draw(im)
        font = _get_font(max(12, min(16, w // 50)))
        line_w = max(1, w // 400)

        anns = _load_image_annotations(batch_dir, image_path, class_names)
        for ann in anns:
            cid = ann["class_id"]
            color = PALETTE[cid % len(PALETTE)]
            x1, y1, x2, y2 = _bbox_to_xyxy(ann["bbox"], w, h)
            draw.rectangle((x1, y1, x2, y2), outline=color, width=line_w)
            label = class_names.get(cid, f"cls_{cid}")
            draw.text((x1 + 2, max(0, y1 - 16)), label, fill=color, font=font)

        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()


# ── Quality Review Model ──

class LabelingReview(Base):
    __tablename__ = "labeling_reviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(64), nullable=False, index=True)
    image_path = Column(String(512), nullable=False)
    score = Column(String(16), nullable=False, default="pending")  # good / fine / bad
    reviewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_name = Column(String(128), nullable=True)
    comment = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "image_path": self.image_path,
            "score": self.score,
            "reviewer_user_id": self.reviewer_user_id,
            "reviewer_name": self.reviewer_name,
            "comment": self.comment,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


# ── Review operations ──

def get_review_queue(campaign_id: str, offset: int = 0, limit: int = 20) -> dict[str, Any]:
    from as_platform.labeling.annotate import resolve_campaign_batch_dir
    from as_platform.db.engine import session_scope
    from as_platform.db.models import LabelingCampaign

    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return {"items": [], "total": 0, "hint": "Campaign 不存在"}
        batch_dir = resolve_campaign_batch_dir(camp)
        class_names = _class_names_for_campaign(camp)
    if not batch_dir or not batch_dir.is_dir():
        return {"items": [], "total": 0, "hint": "批次目录不存在"}

    all_images = _list_review_images(batch_dir)
    if not all_images:
        return {"items": [], "total": 0, "hint": "无 images 目录"}

    # Get existing reviews
    with session_scope() as db:
        reviewed = {
            r.image_path: r.score
            for r in db.query(LabelingReview).filter(LabelingReview.campaign_id == campaign_id).all()
        }

    total = len(all_images)
    page = all_images[offset:offset + limit]
    items = []
    for img in page:
        rel = str(img.relative_to(batch_dir))
        score = reviewed.get(rel, "pending")
        items.append({
            "id": rel, "image_path": rel,
            "fileName": img.name,
            "score": score,
            "has_label": _image_has_labels(batch_dir, img, class_names),
        })

    with session_scope() as db:
        db_counts = _review_db_counts(db, campaign_id)
    reviewed_n = sum(db_counts.values())
    score_counts = {
        "good": db_counts.get("good", 0),
        "fine": db_counts.get("fine", 0),
        "bad": db_counts.get("bad", 0),
        "pending": max(0, total - reviewed_n),
    }

    return {
        "items": items, "total": total,
        "offset": offset, "limit": limit,
        "scores": score_counts,
    }


def get_review_image(campaign_id: str, image_rel_path: str) -> bytes:
    from as_platform.labeling.annotate import resolve_campaign_batch_dir
    from as_platform.db.engine import session_scope
    from as_platform.db.models import LabelingCampaign
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("Campaign 不存在")
        batch_dir = resolve_campaign_batch_dir(camp)
        class_names = _class_names_for_campaign(camp)
    if not batch_dir:
        raise FileNotFoundError("批次不存在")
    img_path = batch_dir / image_rel_path
    if not img_path.is_file():
        raise FileNotFoundError(f"图片不存在: {image_rel_path}")
    return render_review_overlay(img_path, batch_dir, class_names)


def submit_review_scores(
    campaign_id: str,
    scores: list[dict[str, str]],
    reviewer_user_id: int | None = None,
    reviewer_name: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    updated = 0
    with session_scope() as db:
        for item in scores:
            img_path = item["image_path"]
            score = item["score"]
            rec = db.query(LabelingReview).filter(
                LabelingReview.campaign_id == campaign_id,
                LabelingReview.image_path == img_path,
            ).first()
            if rec:
                rec.score = score
                rec.reviewer_user_id = reviewer_user_id
                rec.reviewer_name = reviewer_name
                rec.reviewed_at = now
                rec.comment = item.get("comment")
            else:
                db.add(LabelingReview(
                    campaign_id=campaign_id, image_path=img_path, score=score,
                    reviewer_user_id=reviewer_user_id, reviewer_name=reviewer_name,
                    reviewed_at=now, comment=item.get("comment"),
                ))
            updated += 1
        db.commit()

        # Check if all images are reviewed and auto-advance stage
        counts = _review_db_counts(db, campaign_id)
        from as_platform.labeling.annotate import resolve_campaign_batch_dir
        from as_platform.data.batch import IMG_EXTS
        from as_platform.db.engine import session_scope as _scope
        from as_platform.db.models import LabelingCampaign as _LC
        with _scope() as _db:
            _camp = _db.get(_LC, campaign_id)
            batch_dir = resolve_campaign_batch_dir(_camp) if _camp else None
        total_images = 0
        if batch_dir and (batch_dir / "images").is_dir():
            for ext in IMG_EXTS:
                total_images += len(list((batch_dir / "images").rglob(f"*{ext}")))

        reviewed = sum(counts.values())
        if reviewed >= total_images and total_images > 0:
            new_stage = _effective_stage_from_review(
                counts.get("good", 0), counts.get("fine", 0), counts.get("bad", 0), total_images,
            )
            if new_stage and new_stage != "in_review":
                raw = "review_approved" if new_stage == "labeling_submitted" else new_stage
                _update_campaign_stage(db, campaign_id, raw)

    auto_advanced = reviewed >= total_images if total_images > 0 else False
    acceptable = counts.get("good", 0) + counts.get("fine", 0) if total_images > 0 else 0
    final_stage = None
    if auto_advanced and total_images > 0:
        eff = _effective_stage_from_review(
            counts.get("good", 0), counts.get("fine", 0), counts.get("bad", 0), total_images,
        )
        final_stage = "review_approved" if eff == "labeling_submitted" else eff
    return {
        "ok": True,
        "updated": updated,
        "auto_advanced": auto_advanced,
        "stage": final_stage,
    }


def _review_db_counts(db, campaign_id: str) -> dict[str, int]:
    from sqlalchemy import func
    rows = db.query(LabelingReview.score, func.count()).filter(
        LabelingReview.campaign_id == campaign_id
    ).group_by(LabelingReview.score).all()
    return {score: cnt for score, cnt in rows}


PASS_RATE_THRESHOLD = 0.8


def _effective_stage_from_review(good: int, fine: int, bad: int, total: int) -> str | None:
    """Return campaign status after QA is complete; None if images remain unreviewed."""
    if total <= 0:
        return None
    reviewed = good + fine + bad
    if reviewed < total:
        return "in_review"
    acceptable = good + fine
    approved = acceptable / total >= PASS_RATE_THRESHOLD
    return "labeling_submitted" if approved else "review_rejected"


def reconcile_review_stage(campaign_id: str) -> str | None:
    """Align stored campaign stage with current review scores (fixes stale rejections)."""
    summary = _review_summary(campaign_id)
    if not summary.get("complete"):
        return summary.get("stage")
    expected = _effective_stage_from_review(
        summary["good"], summary["fine"], summary["bad"], summary["total"],
    )
    if not expected:
        return summary.get("stage")
    with session_scope() as db:
        from as_platform.db.models import LabelingCampaign
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return None
        if camp.status == expected:
            return expected
        camp.status = expected
        from as_platform.labeling.batch_stage import update_campaign_batch_meta_stage
        update_campaign_batch_meta_stage(camp, expected)
        db.commit()
        return expected


def _update_campaign_stage(db, campaign_id: str, new_stage: str) -> None:
    from as_platform.db.models import LabelingCampaign
    from as_platform.labeling.batch_stage import update_campaign_batch_meta_stage
    camp = db.get(LabelingCampaign, campaign_id)
    if camp:
        effective = "labeling_submitted" if new_stage == "review_approved" else new_stage
        camp.status = effective
        db.flush()
        update_campaign_batch_meta_stage(camp, effective)


def _review_summary(campaign_id: str) -> dict[str, Any]:
    from as_platform.labeling.annotate import resolve_campaign_batch_dir
    from as_platform.db.models import LabelingCampaign

    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            return {"good": 0, "fine": 0, "bad": 0, "pending": 0, "total": 0, "reviewed": 0, "pass_rate": 0, "complete": False, "stage": ""}
        batch_dir = resolve_campaign_batch_dir(camp)
        stage = camp.status or ""
        if not batch_dir or not batch_dir.is_dir():
            counts = _review_db_counts(db, campaign_id)
            reviewed = sum(counts.values())
            return {
                **{k: counts.get(k, 0) for k in ("good", "fine", "bad")},
                "pending": 0,
                "total": reviewed,
                "reviewed": reviewed,
                "pass_rate": round((counts.get("good", 0) + counts.get("fine", 0)) / max(reviewed, 1) * 100),
                "complete": reviewed > 0,
                "stage": stage,
            }

        all_images = _list_review_images(batch_dir)
        db_counts = _review_db_counts(db, campaign_id)

    total = len(all_images)
    good = db_counts.get("good", 0)
    fine = db_counts.get("fine", 0)
    bad = db_counts.get("bad", 0)
    reviewed = good + fine + bad
    acceptable = good + fine
    return {
        "good": good,
        "fine": fine,
        "bad": bad,
        "pending": max(0, total - reviewed),
        "total": total,
        "reviewed": reviewed,
        "pass_rate": round(acceptable / max(total, 1) * 100),
        "complete": reviewed >= total and total > 0,
        "stage": stage,
    }


def review_progress(campaign_id: str) -> dict[str, Any]:
    result = _review_summary(campaign_id)
    if result.get("complete"):
        reconciled = reconcile_review_stage(campaign_id)
        if reconciled:
            result["stage"] = reconciled
    return result


def review_progress_batch(campaign_ids: list[str]) -> dict[str, Any]:
    ids = [c.strip() for c in campaign_ids if c and c.strip()][:50]
    items: dict[str, Any] = {}
    for cid in ids:
        items[cid] = review_progress(cid)
    return {"items": items}

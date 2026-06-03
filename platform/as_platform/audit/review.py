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
        if ann:
            results.append(ann)
    return results


# ── Optimized overlay render ──

PALETTE = [(220, 20, 60), (30, 144, 255), (50, 205, 50), (255, 165, 0), (186, 85, 211), (0, 206, 209)]


def render_review_overlay(
    image_path: Path,
    label_path: Path | None,
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

        anns = _parse_labels(label_path) if label_path else []
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
    if not batch_dir or not batch_dir.is_dir():
        return {"items": [], "total": 0, "hint": "批次目录不存在"}

    img_dir = batch_dir / "images"
    if not img_dir.is_dir():
        return {"items": [], "total": 0, "hint": "无 images 目录"}

    all_images: list[Path] = []
    for ext in IMAGE_EXTS:
        all_images.extend(sorted(img_dir.rglob(f"*{ext}")))

    # Get existing reviews
    with session_scope() as db:
        reviewed = {
            r.image_path: r.score
            for r in db.query(LabelingReview).filter(LabelingReview.campaign_id == campaign_id).all()
        }

    total = len(all_images)
    page = all_images[offset:offset + limit]
    score_counts = {"good": 0, "fine": 0, "bad": 0, "pending": 0}
    items = []
    for img in page:
        rel = str(img.relative_to(batch_dir))
        score = reviewed.get(rel, "pending")
        score_counts[score] += 1
        label_path = batch_dir / "labels" / (img.stem + ".txt")
        items.append({
            "id": rel, "image_path": rel,
            "fileName": img.name,
            "score": score,
            "has_label": label_path.is_file(),
        })

    # Fill remaining counts
    for img in all_images:
        rel = str(img.relative_to(batch_dir))
        s = reviewed.get(rel, "pending")
        if s not in score_counts:
            score_counts[s] = 0

    return {
        "items": items, "total": total,
        "offset": offset, "limit": limit,
        "scores": score_counts,
    }


def get_review_image(campaign_id: str, image_rel_path: str, class_names: dict[int, str]) -> bytes:
    from as_platform.labeling.annotate import resolve_campaign_batch_dir
    from as_platform.db.engine import session_scope
    from as_platform.db.models import LabelingCampaign
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("Campaign 不存在")
        batch_dir = resolve_campaign_batch_dir(camp)
    if not batch_dir:
        raise FileNotFoundError("批次不存在")
    img_path = batch_dir / image_rel_path
    lbl_path = batch_dir / "labels" / (img_path.stem + ".txt")
    return render_review_overlay(img_path, lbl_path if lbl_path.is_file() else None, class_names)


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
            pass_rate = counts.get("good", 0) / max(total_images, 1)
            new_stage = "review_approved" if pass_rate >= 0.8 else "review_rejected"
            _update_campaign_stage(db, campaign_id, new_stage)

    return {"ok": True, "updated": updated, "auto_advanced": reviewed >= total_images if total_images > 0 else False}


def _review_db_counts(db, campaign_id: str) -> dict[str, int]:
    from sqlalchemy import func
    from collections import Counter
    rows = db.query(LabelingReview.score, func.count()).filter(
        LabelingReview.campaign_id == campaign_id
    ).group_by(LabelingReview.score).all()
    return {score: cnt for score, cnt in rows}


def _update_campaign_stage(db, campaign_id: str, new_stage: str) -> None:
    from as_platform.db.models import LabelingCampaign
    from as_platform.labeling.batch_stage import update_campaign_batch_meta_stage
    camp = db.get(LabelingCampaign, campaign_id)
    if camp:
        camp.status = new_stage
        db.flush()
        update_campaign_batch_meta_stage(camp, new_stage)


def review_progress(campaign_id: str) -> dict[str, int]:
    with session_scope() as db:
        rows = db.query(LabelingReview).filter(LabelingReview.campaign_id == campaign_id).all()
    counts = {"good": 0, "fine": 0, "bad": 0, "pending": 0}
    for r in rows:
        counts[r.score] = counts.get(r.score, 0) + 1
    return counts

"""审核单关联的送标/回传数据：解析范围、列举图像、渲染 GT 叠加。"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml
from PIL import Image, ImageDraw, ImageFont

from as_platform.data.batch import IMG_EXTS
from as_platform.data.core import load_wf, proj_root, resolve_pack_dir

IMAGE_EXTS = tuple(ext.lower() for ext in IMG_EXTS) + tuple(ext.upper() for ext in IMG_EXTS if ext.islower())


@dataclass(frozen=True)
class ImageRef:
    image_path: Path
    label_path: Path | None
    batch: str
    location: str
    split: str

    @property
    def id(self) -> str:
        key = f"{self.image_path}|{self.label_path or ''}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


def _find_image(images_dir: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        p = images_dir / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def _parse_yolo_line(line: str) -> dict[str, Any] | None:
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        class_id = int(float(parts[0]))
        cx, cy, w, h = map(float, parts[1:5])
    except Exception:
        return None
    keypoints: list[tuple[float, float, float]] = []
    rest = parts[5:]
    if len(rest) >= 3:
        n = len(rest) // 3
        for i in range(n):
            keypoints.append((float(rest[i * 3]), float(rest[i * 3 + 1]), float(rest[i * 3 + 2])))
    return {"class_id": class_id, "bbox": (cx, cy, w, h), "keypoints": keypoints}


def parse_label_file(label_path: Path) -> list[dict[str, Any]]:
    if not label_path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in label_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parsed = _parse_yolo_line(raw)
        if parsed is not None:
            out.append(parsed)
    return out


def _load_font(size: int) -> ImageFont.ImageFont:
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _yolo_bbox_to_xyxy(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    cx, cy, bw, bh = bbox
    x1 = int((cx - bw / 2.0) * width)
    y1 = int((cy - bh / 2.0) * height)
    x2 = int((cx + bw / 2.0) * width)
    y2 = int((cy + bh / 2.0) * height)
    return (
        max(0, min(width - 1, x1)),
        max(0, min(height - 1, y1)),
        max(0, min(width - 1, x2)),
        max(0, min(height - 1, y2)),
    )


def render_overlay(
    image_path: Path,
    label_path: Path | None,
    class_names: dict[int, str],
    *,
    max_size: int | None = None,
) -> bytes:
    with Image.open(image_path) as im:
        base = im.convert("RGB")
    if max_size and max(base.size) > max_size:
        base.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    over = base.copy()
    draw = ImageDraw.Draw(over)
    w, h = over.size
    font = _load_font(max(12, min(18, w // 40)))
    anns = parse_label_file(label_path) if label_path else []

    palette = [
        (220, 20, 60),
        (30, 144, 255),
        (50, 205, 50),
        (255, 165, 0),
        (186, 85, 211),
        (0, 206, 209),
    ]
    for ann in anns:
        cid = ann["class_id"]
        color = palette[cid % len(palette)]
        x1, y1, x2, y2 = _yolo_bbox_to_xyxy(ann["bbox"], w, h)
        draw.rectangle((x1, y1, x2, y2), outline=color, width=max(2, w // 320))
        label = class_names.get(cid, f"class_{cid}")
        draw.text((x1 + 2, max(0, y1 - 16)), label, fill=color, font=font)
        for kx, ky, kv in ann.get("keypoints") or []:
            if kv <= 0:
                continue
            px, py = int(kx * w), int(ky * h)
            r = max(2, w // 400)
            draw.ellipse((px - r, py - r, px + r, py + r), outline=color, fill=color)

    buf = io.BytesIO()
    over.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _collect_from_split(batch_dir: Path, split: str, *, batch: str, location: str) -> list[ImageRef]:
    if split:
        images_dir = batch_dir / "images" / split
        labels_dir = batch_dir / "labels" / split
    else:
        images_dir = batch_dir / "images"
        labels_dir = batch_dir / "labels"

    out: list[ImageRef] = []
    if not images_dir.is_dir():
        return out

    label_stems: dict[str, Path] = {}
    if labels_dir.is_dir():
        for lp in labels_dir.glob("*.txt"):
            label_stems[lp.stem] = lp

    seen: set[str] = set()
    for p in sorted(images_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in {e.lower() for e in IMG_EXTS}:
            continue
        stem = p.stem
        seen.add(stem)
        out.append(
            ImageRef(
                image_path=p.resolve(),
                label_path=label_stems.get(stem),
                batch=batch,
                location=location,
                split=split or "root",
            )
        )

    for stem, lp in sorted(label_stems.items()):
        if stem in seen:
            continue
        img = _find_image(images_dir, stem)
        if img:
            out.append(
                ImageRef(
                    image_path=img.resolve(),
                    label_path=lp.resolve(),
                    batch=batch,
                    location=location,
                    split=split or "root",
                )
            )
    return out


def collect_batch_images(batch_dir: Path, *, batch: str, location: str) -> list[ImageRef]:
    if not batch_dir.is_dir():
        return []
    refs: list[ImageRef] = []
    for split in ("train", "val", "test", ""):
        refs.extend(_collect_from_split(batch_dir, split, batch=batch, location=location))
    # 去重（flat 与 train 可能重叠）
    dedup: dict[str, ImageRef] = {}
    for ref in refs:
        dedup[str(ref.image_path)] = ref
    return sorted(dedup.values(), key=lambda r: (r.batch, r.split, r.image_path.name))


def _dms_task_cfg(root: Path, wf: dict, task: str) -> tuple[dict, dict]:
    reg_path = root / wf["projects"]["dms"]["registry"]
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    if task not in reg.get("tasks", {}):
        raise ValueError(f"未知 task: {task}")
    return reg, reg["tasks"][task]


def resolve_approval_scope(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """解析审核单对应的数据目录与类别名。"""
    p = params or {}
    wf = load_wf()

    if action in ("build_dms", "register_batch"):
        task = p.get("task")
        if not task:
            raise ValueError("缺少 task 参数")
        root = proj_root(wf, "dms")
        reg, tcfg = _dms_task_cfg(root, wf, task)
        src_sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
        pack = p.get("pack") or "dms_v2"
        batches: list[dict[str, Any]] = []

        location = p.get("location", "inbox")
        if action == "build_dms" and p.get("all_sources"):
            location = "sources"
        if action == "build_dms" and p.get("batch") and not p.get("all_sources"):
            location = "inbox"

        if location == "inbox":
            batch_name = p.get("batch")
            if batch_name:
                batches.append({"path": root / "inbox" / task / batch_name, "batch": batch_name, "location": "inbox"})
            else:
                ib = root / "inbox" / task
                if ib.is_dir():
                    for d in sorted(ib.iterdir()):
                        if d.is_dir() and not d.name.startswith("."):
                            batches.append({"path": d, "batch": d.name, "location": "inbox"})
        else:
            pack_dir = resolve_pack_dir("dms", root, wf, pack)
            src_root = pack_dir / tcfg.get("task_dir", task) / src_sub
            batch_name = p.get("batch")
            if batch_name:
                batches.append({"path": src_root / batch_name, "batch": batch_name, "location": "sources"})
            elif src_root.is_dir():
                for d in sorted(src_root.iterdir()):
                    if d.is_dir() and d.name not in ("_ingested", "_merged") and not d.name.startswith("."):
                        batches.append({"path": d, "batch": d.name, "location": "sources"})

        names = tcfg.get("names") or {}
        class_names = {int(k): v for k, v in names.items()} if isinstance(names, dict) else {i: n for i, n in enumerate(names)}
        return {
            "project": "dms",
            "task": task,
            "pack": pack,
            "scope_label": f"DMS · {task} · {pack}" + (" · 全部 sources" if location == "sources" and not p.get("batch") else ""),
            "class_names": class_names,
            "batches": batches,
        }

    if action == "build_adas":
        task = p.get("task") or "cuboid_7cls"
        batch_name = p.get("batch")
        root = proj_root(wf, "adas")
        batches: list[dict[str, Any]] = []
        if batch_name:
            batches.append({"path": root / "inbox" / task / batch_name, "batch": batch_name, "location": "inbox"})
        pack = p.get("pack") or "adas_moon3d_v1"
        stats: dict[str, Any] = {}
        if batch_name:
            from as_platform.data.promote.validate.adas_cuboid import validate_adas_cuboid_batch

            bpath = root / "inbox" / task / batch_name
            if bpath.is_dir():
                _err, _warn, stats = validate_adas_cuboid_batch(bpath, allow_partial_3d=True)
        from as_platform.labeling.class_map import load_adas_class_names

        names = load_adas_class_names()
        class_names = {i: n for i, n in enumerate(names)}
        return {
            "project": "adas",
            "task": task,
            "pack": pack,
            "scope_label": f"ADAS · {task} · {pack}" + (f" · {batch_name}" if batch_name else ""),
            "class_names": class_names,
            "batches": batches,
            "export_stats": stats,
        }

    if action == "delivery_ingest":
        data_path = (p.get("data_path") or "").strip()
        if not data_path:
            raise ValueError("缺少 data_path 参数")
        src = Path(data_path)
        project = p.get("project") or "dms"
        task = p.get("task") or ""
        batch_name = p.get("batch_name") or src.name
        scope_label = f"数据送标入湖 · {project}"
        if task:
            scope_label += f" · {task}"
        scope_label += f" · {batch_name}"
        return {
            "project": project,
            "task": task or None,
            "pack": None,
            "scope_label": scope_label,
            "class_names": {},
            "batches": [
                {
                    "path": src,
                    "batch": batch_name,
                    "location": "delivery",
                }
            ],
        }

    if action in ("train_dms", "promote_dms", "eval_dms"):
        task = p.get("task")
        if not task:
            raise ValueError("缺少 task 参数")
        root = proj_root(wf, "dms")
        _, tcfg = _dms_task_cfg(root, wf, task)
        pack = p.get("pack") or "dms_v2"
        pack_dir = resolve_pack_dir("dms", root, wf, pack)
        task_dir = pack_dir / tcfg.get("task_dir", task)
        batches = [{"path": task_dir, "batch": f"{pack}/{task}", "location": "pack"}]
        names = tcfg.get("names") or {}
        class_names = {int(k): v for k, v in names.items()} if isinstance(names, dict) else {i: n for i, n in enumerate(names)}
        label = "模型晋级" if action == "promote_dms" else ("评估" if action == "eval_dms" else "训练")
        return {
            "project": "dms",
            "task": task,
            "pack": pack,
            "scope_label": f"DMS · {task} · {pack} · pack 数据（{label}）",
            "class_names": class_names,
            "batches": batches,
        }

    raise ValueError(f"暂不支持预览的动作: {action}")


def list_scope_images(scope: dict[str, Any], *, offset: int = 0, limit: int = 60) -> dict[str, Any]:
    all_refs: list[ImageRef] = []
    for b in scope.get("batches") or []:
        batch_dir = Path(b["path"])
        all_refs.extend(
            collect_batch_images(batch_dir, batch=b.get("batch", batch_dir.name), location=b.get("location", ""))
        )

    dedup: dict[str, ImageRef] = {str(r.image_path): r for r in all_refs}
    ordered = sorted(dedup.values(), key=lambda r: (r.batch, r.split, r.image_path.name))
    total = len(ordered)
    page = ordered[offset : offset + limit]

    items = []
    for ref in page:
        anns = parse_label_file(ref.label_path) if ref.label_path else []
        items.append(
            {
                "id": ref.id,
                "batch": ref.batch,
                "location": ref.location,
                "split": ref.split,
                "filename": ref.image_path.name,
                "has_label": ref.label_path is not None and ref.label_path.is_file(),
                "box_count": len(anns),
                "missing_label": ref.label_path is None or not ref.label_path.is_file(),
            }
        )
    return {"total": total, "offset": offset, "limit": limit, "items": items}


def find_image_ref(scope: dict[str, Any], image_id: str) -> ImageRef | None:
    """线性查找；审核场景批次有限，可接受。"""
    batches = scope.get("batches") or []
    for b in batches:
        batch_dir = Path(b["path"])
        refs = collect_batch_images(batch_dir, batch=b.get("batch", batch_dir.name), location=b.get("location", ""))
        for ref in refs:
            if ref.id == image_id:
                return ref
    return None


def image_to_item(ref: ImageRef) -> dict[str, Any]:
    anns = parse_label_file(ref.label_path) if ref.label_path else []
    return {
        "id": ref.id,
        "batch": ref.batch,
        "location": ref.location,
        "split": ref.split,
        "filename": ref.image_path.name,
        "has_label": ref.label_path is not None and ref.label_path.is_file(),
        "box_count": len(anns),
        "missing_label": ref.label_path is None or not ref.label_path.is_file(),
        "annotations": [
            {
                "class_id": a["class_id"],
                "class_name": None,
                "bbox": a["bbox"],
                "keypoints": a.get("keypoints") or [],
            }
            for a in anns
        ],
    }

"""Merge train_packs for CLRNet (same layout as UFLD lane0_copy)."""

from __future__ import annotations

import json
from pathlib import Path


def parse_gt_line(line: str) -> tuple[str, str] | None:
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    return parts[0].lstrip("/"), parts[1].lstrip("/")


def load_registry(data_root: Path) -> dict:
    p = data_root / "datasets_registry.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def resolve_pack_dir(pack: str, data_root: Path, registry: dict) -> str:
    aliases = registry.get("aliases", {})
    pack_dirs = registry.get("pack_dirs", {})
    if pack in aliases:
        pack = aliases[pack]
    if pack in pack_dirs:
        pack = pack_dirs[pack]
    if not (data_root / pack).is_dir():
        raise FileNotFoundError(f"pack not found: {data_root / pack} ({pack!r})")
    return pack


def apply_pack_prefix(img: str, msk: str, prefix: str) -> tuple[str, str]:
    if not prefix:
        return img, msk
    if not img.startswith(prefix):
        img = prefix + img
    if not msk.startswith(prefix):
        msk = prefix + msk
    return img, msk


def resolve_list_file(cfg, split: str = "train") -> str | None:
    """Return list path relative to cfg.dataset_path, or None to use defaults."""
    packs_key = "train_packs" if split == "train" else "val_packs"
    packs = getattr(cfg, packs_key, None)
    if not packs:
        return getattr(cfg, f"{split}_list_file", None)

    if isinstance(packs, str):
        packs = [p.strip() for p in packs.split(",") if p.strip()]
    else:
        packs = list(packs)

    data_root = Path(cfg.dataset_path).resolve()
    registry = load_registry(data_root)
    pack_dirs = [resolve_pack_dir(p, data_root, registry) for p in packs]
    list_name = getattr(cfg, "pack_list_name", "list/train_gt.txt")
    if split == "val":
        list_name = getattr(cfg, "pack_val_list_name", "list/val_gt.txt")

    merged_dir = Path(getattr(cfg, "merged_list_dir", "lists_merged"))
    safe = "__".join(pack_dirs)
    out_name = getattr(cfg, f"merged_{split}_list", None) or f"{split}__{safe}.txt"
    out_path = data_root / merged_dir / out_name
    out_rel = (merged_dir / out_name).as_posix()

    if getattr(cfg, "remerge_lists", False) or not out_path.is_file():
        merged = []
        seen = set()
        for pack_dir in pack_dirs:
            prefix = f"{pack_dir}/"
            list_path = data_root / pack_dir / list_name
            if not list_path.is_file():
                raise FileNotFoundError(list_path)
            for line in list_path.read_text(encoding="utf-8", errors="replace").splitlines():
                p = parse_gt_line(line)
                if not p:
                    continue
                img, msk = apply_pack_prefix(p[0], p[1], prefix)
                if img in seen:
                    continue
                seen.add(img)
                merged.append(f"{img} {msk}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(merged) + "\n", encoding="utf-8")

    return out_rel

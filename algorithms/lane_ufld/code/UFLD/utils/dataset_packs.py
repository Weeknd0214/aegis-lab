"""Resolve train_list from config train_packs (DATASET, DATASET-A, ...)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from utils.dist_utils import dist_print, is_main_process


def parse_gt_line(line: str) -> tuple[str, str] | None:
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    return parts[0].lstrip("/"), parts[1].lstrip("/")


def apply_pack_prefix(img: str, msk: str, prefix: str) -> tuple[str, str]:
    if not prefix:
        return img, msk
    if not img.startswith(prefix):
        img = prefix + img
    if not msk.startswith(prefix):
        msk = prefix + msk
    return img, msk


def load_registry(data_root: Path) -> dict:
    path = data_root / "datasets_registry.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_pack_dir(pack: str, data_root: Path, registry: dict) -> str:
    """Map config name (e.g. DATASET-A) to directory name under data_root."""
    aliases = registry.get("aliases", {})
    if pack in aliases:
        pack = aliases[pack]
    pack_dirs = registry.get("pack_dirs", {})
    if pack in pack_dirs:
        pack = pack_dirs[pack]
    pack_path = data_root / pack
    if not pack_path.is_dir():
        raise FileNotFoundError(
            f"pack directory not found: {pack_path} (config train_packs entry: {pack!r})"
        )
    return pack


def pack_list_path(data_root: Path, pack_dir: str, list_name: str) -> Path:
    p = data_root / pack_dir / list_name
    if not p.is_file():
        raise FileNotFoundError(f"pack list not found: {p}")
    return p


def merge_pack_lists(
    data_root: Path,
    pack_dirs: list[str],
    list_name: str,
    out_path: Path,
    *,
    validate: bool = True,
) -> int:
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()

    for pack_dir in pack_dirs:
        prefix = f"{pack_dir}/"
        list_path = pack_list_path(data_root, pack_dir, list_name)
        for line in list_path.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = parse_gt_line(line)
            if not parsed:
                continue
            img, msk = apply_pack_prefix(parsed[0], parsed[1], prefix)
            if img in seen:
                continue
            seen.add(img)
            if validate:
                if not (data_root / img).is_file():
                    raise FileNotFoundError(f"missing image: {data_root / img}")
                if not (data_root / msk).is_file():
                    raise FileNotFoundError(f"missing mask: {data_root / msk}")
            merged.append((img, msk))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(f"{a} {b}" for a, b in merged) + "\n", encoding="utf-8")
    return len(merged)


def merged_list_basename(pack_dirs: list[str]) -> str:
    safe = "__".join(p.replace("/", "_") for p in pack_dirs)
    if len(safe) > 180:
        safe = safe[:180]
    return f"train__{safe}.txt"


def resolve_train_list(cfg) -> str:
    """
    Return train list path relative to cfg.data_root.

    - If cfg.train_packs is set: merge packs and return lists_merged/... path.
    - Else: use cfg.train_list (default list/train_gt.txt).
    """
    train_packs = getattr(cfg, "train_packs", None)
    if not train_packs:
        return getattr(cfg, "train_list", "list/train_gt.txt")

    per_pack_lists: dict = {}
    if isinstance(train_packs, str):
        train_packs = [p.strip() for p in train_packs.split(",") if p.strip()]
    elif isinstance(train_packs, dict):
        per_pack_lists = dict(train_packs)
        train_packs = list(per_pack_lists.keys())
    else:
        train_packs = list(train_packs)

    data_root = Path(cfg.data_root).resolve()
    registry = load_registry(data_root)
    pack_dirs = [resolve_pack_dir(p, data_root, registry) for p in train_packs]

    list_name = getattr(cfg, "pack_list_name", "list/train_gt.txt")
    if per_pack_lists:
        # merge with different list per pack — sequential merge
        merged_dir = Path(getattr(cfg, "merged_list_dir", "lists_merged"))
        out_name = getattr(cfg, "merged_train_list", None) or merged_list_basename(pack_dirs)
        out_path = data_root / merged_dir / out_name
        if is_main_process():
            merged: list[tuple[str, str]] = []
            seen: set[str] = set()
            for pack, pack_dir in zip(train_packs, pack_dirs):
                prefix = f"{pack_dir}/"
                rel_list = per_pack_lists.get(pack, list_name)
                list_path = pack_list_path(data_root, pack_dir, rel_list)
                for line in list_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    parsed = parse_gt_line(line)
                    if not parsed:
                        continue
                    img, msk = apply_pack_prefix(parsed[0], parsed[1], prefix)
                    if img in seen:
                        continue
                    seen.add(img)
                    merged.append((img, msk))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("\n".join(f"{a} {b}" for a, b in merged) + "\n", encoding="utf-8")
            dist_print(f"merged {len(merged)} samples -> {out_path}")
        return str((merged_dir / out_name).as_posix())

    merged_dir = Path(getattr(cfg, "merged_list_dir", "lists_merged"))
    out_name = getattr(cfg, "merged_train_list", None) or merged_list_basename(pack_dirs)
    out_rel = (merged_dir / out_name).as_posix()
    out_path = data_root / merged_dir / out_name

    force = getattr(cfg, "remerge_train_list", False)
    if is_main_process():
        if force or not out_path.is_file():
            n = merge_pack_lists(data_root, pack_dirs, list_name, out_path, validate=True)
            dist_print(f"train_packs {train_packs} -> {n} samples, list={out_rel}")
        else:
            dist_print(f"reuse merged list: {out_rel}")
    return out_rel

#!/usr/bin/env python3
"""
Rename lane0_copy/UFLD assets to a clearer layout and refresh index files.

Conventions
-----------
- Top-level sources: src_<type>_<device>_<YYYYMMDD>  (seg_label/ mirrors the tree)
- Clips: clip_XX, scene_XX, unit_XX, driver_XXX_30fps, video_<id>
- Frames: frame_XXXXXX.jpg / .png (strip legacy _new suffix)
- Camera frames: frame_cam_<id>, frame_ts_<timestamp>

Usage:
  python3 rename_ufld_dataset.py --dry-run
  python3 rename_ufld_dataset.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
UFLD_ROOT = SCRIPT_DIR.parent / "UFLD"

TOP_LEVEL_MAP: dict[str, str] = {
    "100HF": "src_freeway_100hf_day",
    "60HF_night": "src_freeway_60hf_night",
    "crv_lane": "src_vehicle_crv_lane",
    "culane_data": "src_culane",
    "dvr_0422_zxc": "src_dvr_zxc_20250422",
    "dvr_0424_zxc": "src_dvr_zxc_20250424",
    "dvr_0425_buick": "src_dvr_buick_20250425",
    "dvr_0503_buick": "src_dvr_buick_20250503",
    "jiqing_highway": "src_road_jiqing",
    "pic_0507_zk282": "src_cam_zk282_20250507",
    "pic_0511_zk282": "src_cam_zk282_20250511",
    "pic_0514_zk282": "src_cam_zk282_20250514",
    "pic_0613_zk282": "src_cam_zk282_20250613",
    "pic_0620_zxc": "src_cam_zxc_20250620",
    "pic_0624_zxc": "src_cam_zxc_20250624",
    "pic_0628_zxc": "src_cam_zxc_20250628",
    "pic_1009_zk282_front30dig": "src_cam_zk282_20241009_front30deg",
    "pic_1209_zk282": "src_cam_zk282_20241209",
    "pic_250211_zk282": "src_cam_zk282_20250211",
    "pic_250515_zk425": "src_cam_zk425_20250515",
    "pic_250609_zk425": "src_cam_zk425_20250609",
    "shaoyang_data": "src_road_shaoyang",
    "vil": "src_vil",
}

INDEX_FILES = [
    "train_val_gt.txt",
    "test_gt.txt",
    "test.txt",
    "test.json",
    "train_val.json",
    "test_label.json",
]

SKIP_BASENAMES = {
    "train_val_gt.txt",
    "test_gt.txt",
    "test.txt",
    "test.json",
    "train_val.json",
    "test_label.json",
}


def transform_dir_component(name: str) -> str:
    if name in TOP_LEVEL_MAP:
        return TOP_LEVEL_MAP[name]
    m = re.match(r"^scene(\d+)$", name, re.I)
    if m:
        return f"scene_{int(m.group(1)):02d}"
    m = re.match(r"^dvr_(\d+)$", name, re.I)
    if m:
        return f"unit_{int(m.group(1)):02d}"
    m = re.match(r"^(\d+)$", name)
    if m:
        n = int(m.group(1))
        return f"clip_{n:02d}" if n < 1000 else f"clip_{n}"
    m = re.match(r"^driver_(\d+)_30frame$", name, re.I)
    if m:
        return f"driver_{int(m.group(1)):03d}_30fps"
    if name.upper().endswith(".MP4"):
        return "video_" + name[: -len(".MP4")]
    m = re.match(r"^(\d+)_Road(\d+)_Trim(\d+)_frames$", name, re.I)
    if m:
        return f"road_{m.group(2)}_trim_{int(m.group(3)):03d}_seq_{int(m.group(1)):02d}"
    if name == "image_curve":
        return "curve"
    if re.match(r"^highway_\d+$", name):
        return "highway"
    m = re.match(r"^img_(\d+)_(\d+)_batch(\d+)$", name, re.I)
    if m:
        return f"batch_{int(m.group(3)):02d}_stream{int(m.group(2))}"
    m = re.match(r"^pic_(\d+)_([a-z]+)_batch(\d+)$", name, re.I)
    if m:
        return f"batch_{int(m.group(3)):02d}_{m.group(2)}"
    m = re.search(r"batch(\d+)", name, re.I)
    if m and ("batch" in name.lower()):
        return f"batch_{int(m.group(1)):02d}"
    return name


def transform_filename(name: str) -> str:
    if name in SKIP_BASENAMES:
        return name
    base, ext = os.path.splitext(name)
    if ext == ".lines.txt":
        stem = base
        if stem.endswith("_new"):
            stem = stem[: -len("_new")]
        m = re.match(r"^(\d{5})$", stem)
        if m:
            return f"frame_{m.group(1)}.lines.txt"
        return name
    if base.endswith("_new"):
        base = base[: -len("_new")]
    m = re.match(r"^(\d+)$", base)
    if m:
        return f"frame_{int(m.group(1)):06d}{ext}"
    m = re.match(r"^camera_msg_(\d+)$", base, re.I)
    if m:
        return f"frame_cam_{m.group(1)}{ext}"
    m = re.match(r"^camera_front_6mm_(\d+)$", base, re.I)
    if m:
        return f"frame_cam_{m.group(1)}{ext}"
    m = re.match(r"^camera_+(\d+)$", base, re.I)
    if m:
        return f"frame_ts_{m.group(1)}{ext}"
    m = re.match(r"^frame_(\d+)_(\d+)$", base)
    if m:
        return f"frame_{m.group(1)}_{m.group(2)}{ext}"
    m = re.match(r"^frame_(\d+)$", base, re.I)
    if m:
        return f"frame_{int(m.group(1)):06d}{ext}"
    m = re.match(r"^(\d{5})$", base)
    if m:
        return f"frame_{m.group(1)}{ext}"
    return f"{base}{ext}"


def transform_rel_path(rel: str) -> str:
    rel = rel.lstrip("/").replace("\\", "/")
    if not rel:
        return rel
    parts = rel.split("/")
    out: list[str] = []
    i = 0
    if parts[0] == "seg_label":
        out.append("seg_label")
        i = 1
    if i < len(parts):
        out.append(transform_dir_component(parts[i]))
        i += 1
    while i < len(parts):
        comp = parts[i]
        if i == len(parts) - 1:
            out.append(transform_filename(comp))
        else:
            out.append(transform_dir_component(comp))
        i += 1
    return "/".join(out)


def collect_file_mappings(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for dirpath, _, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        for fn in files:
            if fn in SKIP_BASENAMES:
                continue
            old_rel = f"{rel_dir}/{fn}" if rel_dir else fn
            old_rel = old_rel.replace("\\", "/")
            new_rel = transform_rel_path(old_rel)
            if new_rel != old_rel:
                mapping[old_rel] = new_rel
    return mapping


def apply_renames(root: Path, mapping: dict[str, str], dry_run: bool) -> tuple[int, int]:
    ok = 0
    err = 0
    # longest old paths first so nested dirs still resolve
    for old_rel in sorted(mapping.keys(), key=lambda p: (-p.count("/"), p)):
        new_rel = mapping[old_rel]
        old_abs = root / old_rel
        new_abs = root / new_rel
        if not old_abs.is_file():
            continue
        if new_abs.exists() and new_abs.resolve() != old_abs.resolve():
            print(f"COLLISION: {old_rel} -> {new_rel} (target exists)")
            err += 1
            continue
        if dry_run:
            ok += 1
            continue
        new_abs.parent.mkdir(parents=True, exist_ok=True)
        os.rename(old_abs, new_abs)
        ok += 1
    return ok, err


def prune_empty_dirs(root: Path, dry_run: bool) -> int:
    removed = 0
    for dirpath, dirs, files in os.walk(root, topdown=False):
        if not dirs and not files:
            p = Path(dirpath)
            if p == root:
                continue
            if dry_run:
                removed += 1
            else:
                try:
                    p.rmdir()
                    removed += 1
                except OSError:
                    pass
    return removed


def replace_in_line(line: str, mapping: dict[str, str]) -> str:
    out = line
    # Replace longest paths first
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        old_slash = "/" + old
        new_slash = "/" + new
        out = out.replace(old_slash, new_slash)
        if out.startswith(old + " ") or out.startswith(old + "\t"):
            out = new + out[len(old) :]
        if out == old or out.startswith(old + "\n"):
            out = new + out[len(old) :]
    return out


def update_index_files(root: Path, mapping: dict[str, str], dry_run: bool) -> None:
    slash_map = {"/" + k: "/" + v for k, v in mapping.items()}
    slash_map.update(mapping)
    for name in INDEX_FILES:
        path = root / name
        if not path.is_file():
            continue
        if name.endswith(".json"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if dry_run:
                continue
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(path, backup)
            new_text = replace_in_line(text, slash_map)
            path.write_text(new_text, encoding="utf-8")
        else:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            new_lines = [replace_in_line(ln, slash_map) for ln in lines]
            if dry_run:
                continue
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text("".join(new_lines), encoding="utf-8")


def check_collisions(mapping: dict[str, str]) -> list[str]:
    rev: dict[str, list[str]] = defaultdict(list)
    for old, new in mapping.items():
        rev[new].append(old)
    return [f"{new} <= {olds}" for new, olds in rev.items() if len(olds) > 1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=UFLD_ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        args.dry_run = True

    root = args.root.resolve()
    print(f"Root: {root}")
    mapping = collect_file_mappings(root)
    print(f"File path mappings: {len(mapping)}")

    collisions = check_collisions(mapping)
    if collisions:
        print(f"WARNING: {len(collisions)} target collisions (showing 20)")
        for c in collisions[:20]:
            print(" ", c)
        if not args.dry_run:
            raise SystemExit("Abort: fix collisions before apply")

    ok, err = apply_renames(root, mapping, dry_run=args.dry_run)
    print(f"Renames: ok={ok} err={err} dry_run={args.dry_run}")

    if args.apply:
        empty = prune_empty_dirs(root, dry_run=False)
        print(f"Removed {empty} empty directories")
        update_index_files(root, mapping, dry_run=False)
        meta = {
            "root": str(root),
            "files_renamed": ok,
            "mapping_count": len(mapping),
            "top_level_map": TOP_LEVEL_MAP,
        }
        (root / "rename_manifest.json").write_text(
            json.dumps({"meta": meta, "sample": dict(list(mapping.items())[:50])}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("Updated index files (backups: *.bak)")
    else:
        samples = list(mapping.items())[:8]
        for a, b in samples:
            print(f"  {a}\n    -> {b}")


if __name__ == "__main__":
    main()

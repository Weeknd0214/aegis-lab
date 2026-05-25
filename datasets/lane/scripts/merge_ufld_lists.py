#!/usr/bin/env python3
"""
Merge UFLD list files across DATASET + DATASET-AddBy-<engineer>-<date> packs.

When --prefix-from-pack is set, data_root should be lane0_copy (parent of all packs).
Each input list path must live under <pack>/list/*.txt; lines get prefixed as <pack>/images/...

Example:
  python merge_ufld_lists.py \\
    --data-root /home/chengfanglu/DATA/lane0_copy \\
    --prefix-from-pack \\
    --out lists_merged/train_all_v2.txt \\
    --update-registry \\
    DATASET/list/train_gt.txt \\
    DATASET-AddBy-zhangsan-20260615/list/train_gt.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_gt_line(line: str) -> tuple[str, str] | None:
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    img, msk = parts[0].lstrip("/"), parts[1].lstrip("/")
    return img, msk


def resolve_list_path(path: Path, data_root: Path) -> Path:
    if path.is_file():
        return path.resolve()
    candidate = data_root / path
    if candidate.is_file():
        return candidate.resolve()
    sys.exit(f"list not found: {path} (also tried {candidate})")


def pack_prefix_from_list(list_path: Path, data_root: Path) -> str:
    """DATASET/list/train_gt.txt -> DATASET/ ; DATASET-AddBy-x-20260615/list/... -> same."""
    list_path = list_path.resolve()
    data_root = data_root.resolve()
    try:
        rel = list_path.relative_to(data_root)
    except ValueError:
        if list_path.parent.name == "list":
            return f"{list_path.parent.parent.name}/"
        return ""
    if len(rel.parts) >= 2 and rel.parts[1] == "list":
        return f"{rel.parts[0]}/"
    return ""


def apply_pack_prefix(img: str, msk: str, prefix: str) -> tuple[str, str]:
    if not prefix:
        return img, msk
    if not img.startswith(prefix):
        img = prefix + img
    if not msk.startswith(prefix):
        msk = prefix + msk
    return img, msk


def load_pairs(path: Path, prefix: str) -> list[tuple[str, str]]:
    pairs = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = parse_gt_line(line)
        if p:
            pairs.append(apply_pack_prefix(p[0], p[1], prefix))
    return pairs


def validate_pairs(data_root: Path, pairs: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    missing_img, missing_msk = [], []
    for img, msk in pairs:
        if not (data_root / img).is_file():
            missing_img.append(img)
        if not (data_root / msk).is_file():
            missing_msk.append(msk)
    return missing_img, missing_msk


def update_registry(registry_path: Path, data_root: Path, out_rel: str, input_paths: list[Path]) -> None:
    if registry_path.is_file():
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        reg = {
            "schema": "ufld-multi-pack-v1",
            "parent_root": str(data_root),
            "base_pack": "DATASET",
            "packs": [],
            "merged_train_lists": {},
        }
    reg["parent_root"] = str(data_root)
    known = {p["name"] for p in reg.get("packs", [])}
    for lp in input_paths:
        prefix = pack_prefix_from_list(lp, data_root)
        name = prefix.rstrip("/") if prefix else lp.parent.parent.name
        if name and name not in known:
            reg.setdefault("packs", []).append(
                {"name": name, "path": name, "role": "increment" if name != "DATASET" else "baseline_v1"}
            )
            known.add(name)
    reg.setdefault("merged_train_lists", {})[Path(out_rel).name] = {
        "path": out_rel.replace("\\", "/"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [str(resolve_list_path(p, data_root)) for p in input_paths],
    }
    registry_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge UFLD lists across DATASET / DATASET-AddBy-* packs")
    ap.add_argument(
        "--data-root",
        type=Path,
        required=True,
        help="parent dir containing DATASET and DATASET-AddBy-* (e.g. lane0_copy)",
    )
    ap.add_argument("--out", type=Path, required=True, help="output list, e.g. lists_merged/train_all_v2.txt")
    ap.add_argument("inputs", nargs="+", type=Path, help="pack list files, e.g. DATASET/list/train_gt.txt")
    ap.add_argument("--base", type=Path, default=None, help="processed first; duplicates skipped")
    ap.add_argument(
        "--prefix-from-pack",
        action="store_true",
        help="prefix each line with pack dir name inferred from input path",
    )
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument(
        "--update-registry",
        action="store_true",
        help="update datasets_registry.json under data-root",
    )
    args = ap.parse_args()

    data_root = args.data_root.resolve()
    ordered: list[tuple[str, Path]] = []
    if args.base:
        ordered.append(("base", resolve_list_path(args.base, data_root)))
    for i, p in enumerate(args.inputs):
        ordered.append((f"input{i}", resolve_list_path(p, data_root)))

    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    stats: dict = {"sources": {}}

    for name, list_path in ordered:
        prefix = pack_prefix_from_list(list_path, data_root) if args.prefix_from_pack else ""
        added = skipped = 0
        for img, msk in load_pairs(list_path, prefix):
            if img in seen:
                skipped += 1
                continue
            seen.add(img)
            merged.append((img, msk))
            added += 1
        stats["sources"][str(list_path)] = {
            "pack_prefix": prefix,
            "added": added,
            "skipped_duplicate": skipped,
        }

    if not args.no_validate:
        missing_img, missing_msk = validate_pairs(data_root, merged)
        stats["missing_images"] = len(missing_img)
        stats["missing_masks"] = len(missing_msk)
        if missing_img or missing_msk:
            print(f"ERROR: missing {len(missing_img)} images, {len(missing_msk)} masks", file=sys.stderr)
            for p in missing_img[:10]:
                print("  img:", p, file=sys.stderr)
            for p in missing_msk[:10]:
                print("  msk:", p, file=sys.stderr)
            sys.exit(1)

    out_path = args.out if args.out.is_absolute() else data_root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(f"{img} {msk}" for img, msk in merged) + "\n", encoding="utf-8")

    stats["total_out"] = len(merged)
    stats["data_root"] = str(data_root)
    stats["output"] = str(out_path)
    stats["prefix_from_pack"] = args.prefix_from_pack
    stats["created_utc"] = datetime.now(timezone.utc).isoformat()

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"Wrote {len(merged)} pairs -> {out_path}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.update_registry:
        out_rel = str(out_path.relative_to(data_root)).replace("\\", "/")
        update_registry(
            data_root / "datasets_registry.json",
            data_root,
            out_rel,
            [p for _, p in ordered],
        )
        print(f"Updated {data_root / 'datasets_registry.json'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Build one incremental UFLD pack: DATASET-AddBy-<engineer>-<date>

Wrapper around build_ufld_dataset layout logic; does not modify base DATASET/.

Example:
  python build_ufld_pack.py \\
    --src /path/to/archive \\
    --parent /home/chengfanglu/DATA/lane0_copy \\
    --engineer zhangsan \\
    --date 20260615
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def sanitize_engineer(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("engineer name is empty")
    if not re.match(r"^[A-Za-z0-9_\-]+$", name):
        raise ValueError("engineer: use letters, digits, underscore, hyphen only")
    return name


def pack_name(engineer: str, date: str) -> str:
    date = re.sub(r"[^0-9]", "", date)
    if len(date) != 8:
        raise ValueError("date must be YYYYMMDD (8 digits)")
    return f"DATASET-AddBy-{engineer}-{date}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Build DATASET-AddBy-<engineer>-<date> pack")
    ap.add_argument("--src", type=Path, required=True, help="archive with train_val_gt.txt")
    ap.add_argument("--parent", type=Path, default=Path("/home/chengfanglu/DATA/lane0_copy"))
    ap.add_argument("--engineer", type=str, required=True)
    ap.add_argument("--date", type=str, required=True, help="YYYYMMDD")
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    engineer = sanitize_engineer(args.engineer)
    out_name = pack_name(engineer, args.date)
    out_root = args.parent.resolve() / out_name

    if out_root.exists() and any(out_root.iterdir()):
        sys.exit(f"Refusing to overwrite non-empty pack: {out_root}")

    build_script = SCRIPT_DIR / "build_ufld_dataset.py"
    cmd = [
        sys.executable,
        str(build_script),
        "--src",
        str(args.src.resolve()),
        "--out",
        str(out_root),
        "--val-ratio",
        str(args.val_ratio),
        "--seed",
        str(args.seed),
    ]
    if args.copy:
        cmd.append("--copy")

    print(f"Building pack: {out_name}", file=sys.stderr)
    subprocess.check_call(cmd)

    # annotate manifest
    manifest_path = out_root / "manifest.json"
    if manifest_path.is_file():
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["pack_name"] = out_name
        manifest["engineer"] = engineer
        manifest["pack_date"] = re.sub(r"[^0-9]", "", args.date)
        manifest["layout"] = "DATASET-AddBy-<engineer>-<date>"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(f"Done: {out_root}")


if __name__ == "__main__":
    main()

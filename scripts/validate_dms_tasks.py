#!/usr/bin/env python3
"""检查 DMS：yaml_active + active_packs 下数据。--task 仅查单任务。失败 exit 1。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

WORKSPACE = Path(__file__).resolve().parents[1]
DATASET = (WORKSPACE / "datasets/dms").resolve()


def load_context():
    reg = yaml.safe_load((DATASET / "datasets.registry.yaml").read_text())
    wf = yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text())
    active = wf["projects"]["dms"]["active_packs"]
    sys.path.insert(0, str(DATASET / "scripts"))
    from pack_registry import resolve_pack_dir  # noqa: E402
    return reg, active, resolve_pack_dir


def check_yolo(data_dir: Path) -> list[str]:
    errs = []
    for sp in ("train", "val"):
        img_d = data_dir / "images" / sp
        lab_d = data_dir / "labels" / sp
        if not img_d.is_dir():
            errs.append(f"missing {img_d}")
            continue
        imgs = {p.stem for p in img_d.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}}
        labs = {p.stem for p in lab_d.glob("*.txt")} if lab_d.is_dir() else set()
        if imgs != labs:
            errs.append(f"{sp}: img/label mismatch ({len(imgs)} vs {len(labs)})")
    return errs


def validate_task(task: str, tcfg: dict, active: list, resolve_pack_dir, errors: list) -> None:
    yml = DATASET / "manifests" / "yaml_active" / f"{task}.yaml"
    if not yml.is_file():
        errors.append(f"{task}: missing yaml_active {yml}")
        return
    for pack in active:
        base = resolve_pack_dir(DATASET, pack) / tcfg["task_dir"]
        if not base.is_dir():
            errors.append(f"{task}/{pack}: missing {base}")
            continue
        if tcfg["type"] in ("detect", "pose"):
            errors.extend(f"{task}/{pack}: {e}" for e in check_yolo(base))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task")
    args = ap.parse_args()
    reg, active, resolve_pack_dir = load_context()
    print(f"active_packs: {active}")

    tasks = reg["tasks"]
    if args.task:
        if args.task not in tasks:
            print(f"未知 task: {args.task}", file=sys.stderr)
            return 1
        tasks = {args.task: tasks[args.task]}

    errors: list[str] = []
    for task, tcfg in tasks.items():
        print(f"\n{task} ({tcfg['type']})")
        validate_task(task, tcfg, active, resolve_pack_dir, errors)

    if errors:
        print("\nFAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("\nvalidate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

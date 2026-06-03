#!/usr/bin/env python3
"""按 workflow active_packs 生成 manifests/yaml_active/*.yaml（可多包合并 train/val）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from pack_registry import load_active_pack_names, resolve_pack_dir  # noqa: E402
from task_registry import get_mode_config, load_registry, train_yaml_key  # noqa: E402


def fmt_names(names) -> str:
    if isinstance(names, dict):
        lines = ["names:"]
        for k, v in sorted(names.items(), key=lambda x: int(x[0])):
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
    inner = ", ".join(f'"{n}"' for n in names)
    return f"names: [{inner}]"


def yaml_list(key: str, paths: list[str]) -> str:
    if len(paths) == 1:
        return f"{key}: {paths[0]}"
    lines = [f"{key}:"] + [f"  - {p}" for p in paths]
    return "\n".join(lines)


def pack_task_root(root: Path, pack_name: str, task_dir: str) -> Path:
    return resolve_pack_dir(root, pack_name) / task_dir


def build_detect_pose_yaml(
    yaml_key: str,
    mcfg: dict,
    root: Path,
    pack_names: list[str],
    typ: str,
) -> str:
    task_dir = mcfg["task_dir"]
    bases = []
    train_paths = []
    val_paths = []
    for pack in pack_names:
        base = pack_task_root(root, pack, task_dir)
        if not base.is_dir():
            print(f"  skip pack {pack}: missing {base}")
            continue
        bases.append(base)
        train_paths.append(str((base / "images" / "train").resolve()))
        val_paths.append(str((base / "images" / "val").resolve()))

    if not bases:
        raise SystemExit(f"{yaml_key}: 无可用数据包目录")

    lines = [
        f"# {yaml_key} — packs: {', '.join(pack_names)}",
        f"path: {bases[0]}",
        yaml_list("train", train_paths),
        yaml_list("val", val_paths),
        "",
    ]
    if typ == "pose":
        lines.insert(4, f"kpt_shape: {mcfg.get('kpt_shape', [37, 3])}")
    else:
        lines.extend([f"nc: {mcfg['nc']}", fmt_names(mcfg["names"]), ""])
    return "\n".join(lines)


def build_classify_yaml(yaml_key: str, mcfg: dict, root: Path, pack_names: list[str]) -> str:
    task_dir = mcfg["task_dir"]
    if len(pack_names) > 1:
        print(f"  warn {yaml_key}: classify 暂用首个包 {pack_names[0]}（多包请先合并目录）")
    base = pack_task_root(root, pack_names[0], task_dir)
    return f"""# {yaml_key} — pack: {pack_names[0]}
path: {base.resolve()}
train: train
val: val
test: test
"""


def iter_yaml_jobs(reg: dict, only_task: str | None = None):
    tasks = load_registry(reg)
    if only_task:
        if only_task not in tasks:
            raise SystemExit(f"未知 task: {only_task}")
        tasks = {only_task: tasks[only_task]}
    for task, tcfg in tasks.items():
        if tcfg.get("type") == "multi":
            for mode in (tcfg.get("modes") or {}):
                mcfg = get_mode_config(task, mode, reg)
                key = train_yaml_key(task, mode, reg)
                yield key, mcfg
        else:
            yield task, tcfg


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=SCRIPT_DIR.parent)
    p.add_argument("--packs", help="逗号分隔，覆盖 workflow active_packs")
    p.add_argument("--task", help="只生成某一任务（multi 会生成全部 mode）")
    args = p.parse_args()
    root = args.root.resolve()
    reg = yaml.safe_load((root / "datasets.registry.yaml").read_text(encoding="utf-8"))
    cli = [x.strip() for x in args.packs.split(",")] if args.packs else None
    pack_names = load_active_pack_names(root, cli)
    if not pack_names:
        raise SystemExit("active_packs 为空，请编辑 workflow.registry.yaml 或 --packs")

    out_dir = root / "manifests" / "yaml_active"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"active_packs: {pack_names}")

    for yaml_key, mcfg in iter_yaml_jobs(reg, args.task):
        typ = mcfg["type"]
        if typ in ("detect", "pose"):
            content = build_detect_pose_yaml(yaml_key, mcfg, root, pack_names, typ)
        elif typ == "classify":
            content = build_classify_yaml(yaml_key, mcfg, root, pack_names)
        else:
            print(f"  skip {yaml_key}: type {typ}")
            continue
        out = out_dir / f"{yaml_key}.yaml"
        out.write_text(content, encoding="utf-8")
        print(f"  wrote {out.relative_to(root)}")

    print("完成。")


if __name__ == "__main__":
    main()

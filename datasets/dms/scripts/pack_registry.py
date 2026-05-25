"""DMS 多包：data_packs.yaml + ML/workflow.registry.yaml active_packs。"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_packs_registry(root: Path) -> dict:
    p = root / "data_packs.yaml"
    if not p.is_file():
        raise SystemExit(f"缺少 {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def ml_workflow_path(dataset_root: Path) -> Path:
    # workspace/DMS/DATASET -> DATA/HSAP/workflow.registry.yaml
    return dataset_root.resolve().parent.parent.parent / "ML" / "workflow.registry.yaml"


def load_active_pack_names(dataset_root: Path, cli_packs: list[str] | None = None) -> list[str]:
    if cli_packs:
        return cli_packs
    wf_path = ml_workflow_path(dataset_root)
    if wf_path.is_file():
        wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        active = wf.get("projects", {}).get("dms", {}).get("active_packs")
        if active:
            return list(active)
    reg = load_packs_registry(dataset_root)
    return [reg["packs"][0]["name"]] if reg.get("packs") else []


def resolve_pack_dir(root: Path, pack_name: str) -> Path:
    reg = load_packs_registry(root)
    name = reg.get("aliases", {}).get(pack_name, pack_name)
    for item in reg.get("packs", []):
        if item.get("name") == name:
            return (root / item["path"]).resolve()
    candidate = root / name
    if candidate.is_dir():
        return candidate.resolve()
    raise SystemExit(f"未知数据包: {pack_name}，已登记: {[p['name'] for p in reg.get('packs', [])]}")


def task_data_root(dataset_root: Path, pack_name: str, task_dir: str) -> Path:
    return resolve_pack_dir(dataset_root, pack_name) / task_dir


def list_registered_packs(root: Path) -> list[dict]:
    return load_packs_registry(root).get("packs", [])

"""DMS 任务注册表：domain 分组、multi 任务（前向 detect+classify）、旧 ID 别名。"""
from __future__ import annotations

from typing import Any

DOMAIN_LABELS = {
    "dms": "舱内 DMS",
    "forward": "前向 ADAS",
}

# 报表 / 旧目录名 -> (task, mode)
REPORT_TASK_ALIASES: dict[str, tuple[str, str | None]] = {
    "isa": ("forward", "detect"),
    "isa_detect": ("forward", "detect"),
    "isa_class": ("forward", "classify"),
    "isa_class_0116": ("forward", "classify"),
    "dam_0417": ("dam", "batch_0417"),
}

LEGACY_TASK_ALIASES: dict[str, tuple[str, str | None]] = {
    "isa": ("forward", "detect"),
    "isa_class": ("forward", "classify"),
    "dam_0417": ("dam", "batch_0417"),
}


def load_registry(reg: dict) -> dict[str, Any]:
    return reg.get("tasks") or {}


def resolve_task_id(task: str, mode: str | None = None) -> tuple[str, str | None]:
    """用户/历史 task ID -> (canonical_task, mode)。"""
    if task in LEGACY_TASK_ALIASES:
        t, m = LEGACY_TASK_ALIASES[task]
        return t, mode or m
    return task, mode


def report_task_key(task: str, mode: str | None = None) -> str:
    """catalog 报表 CSV 中的任务列名。"""
    t, m = resolve_task_id(task, mode)
    if t == "forward" and m == "detect":
        return "isa"
    if t == "forward" and m == "classify":
        return "isa_class"
    if t == "dam" and m == "batch_0516":
        return "dam"
    if t == "dam" and m == "batch_0417":
        return "dam_0417"
    return task


def train_yaml_key(task: str, mode: str | None, reg: dict) -> str:
    """manifests/yaml_active 与 train.sh 使用的文件名（不含 .yaml）。"""
    task, mode = resolve_task_id(task, mode)
    tcfg = load_registry(reg)[task]
    if tcfg.get("type") == "multi":
        if not mode:
            raise ValueError(f"任务 {task} 需指定 mode（detect / classify）")
        return f"{task}__{mode}"
    return task


def get_mode_config(task: str, mode: str | None, reg: dict) -> dict[str, Any]:
    task, mode = resolve_task_id(task, mode)
    tcfg = load_registry(reg)[task]
    if tcfg.get("type") != "multi":
        return {**tcfg, "task": task, "mode": None}
    modes = tcfg.get("modes") or {}
    if not mode:
        raise ValueError(f"任务 {task} 需指定 mode")
    if mode not in modes:
        raise ValueError(f"未知 mode: {task}/{mode}")
    mcfg = dict(modes[mode])
    mcfg["task"] = task
    mcfg["mode"] = mode
    mcfg["task_dir"] = f"{tcfg.get('task_dir', task)}/{mcfg.get('subdir', mode)}"
    mcfg["domain"] = tcfg.get("domain")
    mcfg["label"] = mcfg.get("label") or tcfg.get("label")
    return mcfg


def task_data_dir(pack_dir, task: str, mode: str | None, reg: dict):
    from pathlib import Path

    mcfg = get_mode_config(task, mode, reg)
    return Path(pack_dir) / mcfg["task_dir"]


def inbox_dir(root, task: str, mode: str | None, reg: dict):
    from pathlib import Path

    task, mode = resolve_task_id(task, mode)
    tcfg = load_registry(reg)[task]
    if tcfg.get("type") == "multi":
        mcfg = tcfg["modes"][mode or ""]
        rel = mcfg.get("inbox") or f"inbox/{task}/{mode}"
        return Path(root) / rel
    return Path(root) / (tcfg.get("inbox") or f"inbox/{task}")


def iter_catalog_tasks(reg: dict) -> list[tuple[str, dict[str, Any]]]:
    """catalog 顶层任务列表。"""
    out: list[tuple[str, dict[str, Any]]] = []
    for task, tcfg in load_registry(reg).items():
        entry = {
            "domain": tcfg.get("domain", "dms"),
            "domain_label": DOMAIN_LABELS.get(tcfg.get("domain", "dms"), tcfg.get("domain", "dms")),
            "label": tcfg.get("label", task),
            "type": tcfg.get("type"),
        }
        if tcfg.get("type") == "multi":
            entry["modes"] = {}
            for mode, mcfg in (tcfg.get("modes") or {}).items():
                entry["modes"][mode] = {
                    "label": mcfg.get("label", mode),
                    "type": mcfg.get("type"),
                    "nc": mcfg.get("nc"),
                    "names": mcfg.get("names"),
                    "packs": [],
                    "class_counts": {},
                }
        else:
            entry["nc"] = tcfg.get("nc")
            entry["names"] = tcfg.get("names")
            entry["packs"] = []
            entry["class_counts"] = {}
        out.append((task, entry))
    return out


def map_report_task(report_name: str) -> tuple[str, str | None]:
    if report_name in REPORT_TASK_ALIASES:
        return REPORT_TASK_ALIASES[report_name]
    return report_name, None


def task_defs_for_pending(reg: dict) -> dict[str, Any]:
    """平台 pending API 的 task_defs。"""
    defs: dict[str, Any] = {}
    for task, tcfg in load_registry(reg).items():
        if tcfg.get("type") == "multi":
            defs[task] = {
                "type": "multi",
                "domain": tcfg.get("domain", "dms"),
                "label": tcfg.get("label", task),
                "modes": {
                    m: {
                        "type": mc.get("type"),
                        "nc": mc.get("nc"),
                        "names": mc.get("names"),
                        "task_dir": f"{tcfg.get('task_dir', task)}/{mc.get('subdir', m)}",
                    }
                    for m, mc in (tcfg.get("modes") or {}).items()
                },
            }
        else:
            defs[task] = {
                "type": tcfg.get("type"),
                "domain": tcfg.get("domain", "dms"),
                "label": tcfg.get("label", task),
                "nc": tcfg.get("nc"),
                "names": tcfg.get("names"),
                "task_dir": tcfg.get("task_dir", task),
            }
    return defs

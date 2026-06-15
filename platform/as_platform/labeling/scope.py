"""CatalogScope 与 registry 对齐。"""
from __future__ import annotations

from typing import Any

import yaml

from as_platform.config import WORKSPACE

DOMAIN_LABELS = {"dms": "舱内 DMS", "forward": "前向 ADAS"}


def format_scope_key(project: str, task: str, mode: str | None = None) -> str:
    if project == "adas":
        return f"adas:{task}"
    if project == "lane":
        return f"lane:{task}"
    if mode:
        return f"dms:{task}:{mode}"
    return f"dms:{task}"


def _dms_registry_api():
    import sys
    from pathlib import Path
    p = WORKSPACE / "datasets" / "dms" / "scripts"
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    from task_registry import get_mode_config, resolve_task_id, train_yaml_key
    return get_mode_config, resolve_task_id, train_yaml_key


def load_dms_registry() -> dict:
    path = WORKSPACE / "datasets" / "dms" / "datasets.registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_labeling_registry() -> dict[str, Any]:
    path = WORKSPACE / "datasets" / "labeling.registry.yaml"
    if not path.is_file():
        return {"profiles": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"profiles": {}}


def labeling_profile_key(project: str, task: str, mode: str | None, reg: dict | None = None) -> str:
    if project == "adas":
        return task
    if project == "lane":
        return f"lane__{task}"
    get_mode_config, resolve_task_id, train_yaml_key = _dms_registry_api()
    reg = reg or load_dms_registry()
    task, mode = resolve_task_id(task, mode)
    return train_yaml_key(task, mode, reg)


def enrich_batch_labels(batch: dict[str, Any], reg: dict | None = None) -> dict[str, Any]:
    project = batch.get("project") or "dms"
    task = batch.get("task") or ""
    mode = batch.get("mode")
    out = dict(batch)
    out["scope_key"] = format_scope_key(project, task, mode)
    if project == "dms":
        reg = reg or load_dms_registry()
        get_mode_config, resolve_task_id, _ = _dms_registry_api()
        try:
            task_r, mode_r = resolve_task_id(task, mode)
            mcfg = get_mode_config(task_r, mode_r, reg)
            domain = mcfg.get("domain") or "dms"
            out["domain"] = domain
            out["domain_label"] = DOMAIN_LABELS.get(domain, domain)
            out["task_label"] = mcfg.get("label") or task
            if mode_r:
                modes = (reg.get("tasks") or {}).get(task_r, {}).get("modes") or {}
                out["mode_label"] = (modes.get(mode_r) or {}).get("label") or mode_r
        except Exception:
            out["domain"] = "dms"
            out["domain_label"] = DOMAIN_LABELS["dms"]
    elif project == "adas":
        out["domain"] = "adas"
        out["domain_label"] = "前向 ADAS"
        out["task_label"] = task
    else:
        out["domain_label"] = "车道线 Lane"
        out["task_label"] = task
    try:
        pk = labeling_profile_key(project, task, mode, reg if project == "dms" else None)
        out["labeling_profile"] = pk
        prof = (load_labeling_registry().get("profiles") or {}).get(pk)
        if prof:
            out["export_default"] = prof.get("export_default")
            out["ml_adapter"] = prof.get("ml_adapter")
    except Exception:
        out["labeling_profile"] = None
    return out

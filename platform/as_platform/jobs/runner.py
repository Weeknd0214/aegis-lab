"""执行动作：优先引擎适配器，fallback as.py CLI。"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from as_platform.config import WORKSPACE, PLATFORM_DIR, LANE_DATA_VIZ_ENABLED

if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

ML_PY = WORKSPACE / "as.py"
AS_PY = ML_PY

LONG_ACTIONS = {"train_dms", "train_lane", "pipeline_dms", "eval_dms", "eval_lane", "visualize_dms", "visualize_lane"}


def _run_ml(argv: list[str], timeout: int = 7200) -> dict[str, Any]:
    cmd = [sys.executable, str(ML_PY), *argv]
    proc = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"as.py 失败 (exit {proc.returncode}):\n{proc.stderr or proc.stdout}")
    return {"ok": True, "stdout": proc.stdout, "stderr": proc.stderr, "command": " ".join(cmd)}


def execute_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    p = params or {}

    if action == "train_dms":
        track = p.get("track", "platform")
        if track == "local":
            from algorithms.dms_yolo.adapter import train_local
            return train_local(p["task"], p.get("mode", "full"), p.get("config_overrides"))
        from algorithms.dms_yolo.adapter import train_platform
        return train_platform(p["task"], p.get("mode", "full"))

    if action == "train_lane":
        track = p.get("track", "platform")
        if track == "local":
            from algorithms.lane_ufld.adapter import train_local
            return train_local(p.get("config_overrides"))
        from algorithms.lane_ufld.adapter import train_platform
        return train_platform()

    if action == "train_dms_legacy":
        argv = ["train", "dms", p["task"]]
        if p.get("mode"):
            argv.extend(["--mode", str(p["mode"])])
        return _run_ml(argv, timeout=86400)

    if action == "train_lane_legacy":
        return _run_ml(["train", "lane"], timeout=86400)

    if action == "build_dms":
        argv = ["build", "dms", p["task"]]
        if p.get("pack"):
            argv.extend(["--pack", str(p["pack"])])
        if p.get("batch"):
            argv.extend(["--batch", str(p["batch"])])
        if p.get("all_sources"):
            argv.append("--all-sources")
        if p.get("dry_run"):
            argv.append("--dry-run")
        if p.get("skip_validate"):
            argv.append("--skip-validate")
        if p.get("no_refresh"):
            argv.append("--no-refresh")
        return _run_ml(argv)

    if action == "build_lane":
        return _run_ml(["build", "lane"])

    if action == "enable_pack":
        return _run_ml(["enable", p["project"], p["pack"]])

    if action == "disable_pack":
        return _run_ml(["disable", p["project"], p["pack"]])

    if action == "eval_dms":
        argv = ["eval", "dms", p["task"]]
        if p.get("save_candidate"):
            argv.append("--save-candidate")
        if p.get("weights"):
            argv.extend(["--weights", str(p["weights"])])
        return _run_ml(argv, timeout=3600)

    if action == "eval_lane":
        from algorithms.lane_ufld.adapter import eval_task

        return eval_task(
            model_path=p.get("model_path"),
            data_root=p.get("data_root"),
            test_list=p.get("test_list", "list/test_gt.txt"),
        )

    if action == "visualize_dms":
        from algorithms.dms_yolo.adapter import visualize_task

        return visualize_task(
            p["task"],
            weights=p.get("weights"),
        )

    if action == "visualize_lane":
        if not LANE_DATA_VIZ_ENABLED:
            raise RuntimeError("车道线数据可视化暂未开放")
        from algorithms.lane_ufld.adapter import visualize_task

        return visualize_task(
            model_path=p.get("model_path"),
            data_root=p.get("data_root"),
            test_list=p.get("test_list", "list/test_gt.txt"),
        )

    if action == "promote_dms":
        argv = ["promote", "dms", p["task"]]
        if p.get("force"):
            argv.append("--force")
        return _run_ml(argv)

    if action == "pipeline_dms":
        argv = ["pipeline", "dms", p["task"], "--pack", str(p.get("pack", "dms_v2"))]
        if p.get("batch"):
            argv.extend(["--batch", str(p["batch"])])
        if p.get("all_sources"):
            argv.append("--all-sources")
        if p.get("train"):
            argv.append("--train")
        if p.get("dry_run"):
            argv.append("--dry-run")
        return _run_ml(argv, timeout=86400)

    if action == "register_batch":
        from as_platform.data.core import register_batch

        register_batch(
            None, p["project"], p.get("task"), p["batch"],
            pack=p.get("pack"), stage=p.get("stage", "returned"),
            engineer=p.get("engineer"), location=p.get("location", "inbox"),
        )
        return {"ok": True, "stdout": "register_batch ok", "stderr": ""}

    if action == "analyze_uploaded_dataset":
        from as_platform.data.lake import analyze_uploaded_candidate

        candidate_id = p["candidate_id"]
        result = analyze_uploaded_candidate(candidate_id)
        return {
            "ok": True,
            "stdout": json.dumps(result, ensure_ascii=False),
            "stderr": "",
            "result": result,
        }

    raise ValueError(f"未实现执行: {action}")

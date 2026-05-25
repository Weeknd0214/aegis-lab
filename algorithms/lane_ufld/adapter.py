"""Lane UFLD 引擎适配。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

WORKSPACE = Path(__file__).resolve().parents[2]


def _lane_workdir() -> Path:
    wf = yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text(encoding="utf-8"))
    return (WORKSPACE / wf["projects"]["lane"]["train"]["workdir"]).resolve()


def _latest_lane_weights(workdir: Path) -> str | None:
    candidates = sorted(workdir.rglob("best.pth"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    return str(candidates[0].resolve())


def train_local(config_overrides: dict | None = None) -> dict[str, Any]:
    wd = _lane_workdir()
    cfg = yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text())["projects"]["lane"]["train"]["config"]
    proc = subprocess.run(
        [sys.executable, "train.py", cfg],
        cwd=str(wd),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "track": "local",
        "workdir": str(wd),
        "command": f"{sys.executable} train.py {cfg}",
        "best_weights": _latest_lane_weights(wd),
    }


def train_platform() -> dict[str, Any]:
    wd = _lane_workdir()
    wf = yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text(encoding="utf-8"))
    cfg = wf["projects"]["lane"]["train"]["config"]
    proc = subprocess.run([sys.executable, "train.py", cfg], cwd=str(wd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "track": "platform",
        "workdir": str(wd),
        "command": f"{sys.executable} train.py {cfg}",
        "best_weights": _latest_lane_weights(wd),
    }


def eval_task(model_path: str | None = None, data_root: str | None = None, test_list: str = "list/test_gt.txt") -> dict[str, Any]:
    if not model_path:
        raise ValueError("lane eval 需要 model_path（best.pth）")
    wd = _lane_workdir()
    wf = yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text(encoding="utf-8"))
    cfg = wf["projects"]["lane"]["train"]["config"]
    root = data_root or str((WORKSPACE / wf["projects"]["lane"]["root"]).resolve())
    model = model_path
    cmd = [sys.executable, "test.py", cfg, "--test_model", model, "--data_root", root, "--test_list", test_list]
    proc = subprocess.run(cmd, cwd=str(wd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "workdir": str(wd),
        "command": " ".join(cmd),
        "model_path": model,
    }


def visualize_task(model_path: str | None = None, data_root: str | None = None, test_list: str = "list/test_gt.txt") -> dict[str, Any]:
    if not model_path:
        raise ValueError("lane visualize 需要 model_path（best.pth）")
    wd = _lane_workdir()
    wf = yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text(encoding="utf-8"))
    cfg = wf["projects"]["lane"]["train"]["config"]
    root = data_root or str((WORKSPACE / wf["projects"]["lane"]["root"]).resolve())
    model = model_path
    cmd = [sys.executable, "demo.py", cfg, "--test_model", model, "--data_root", root]
    proc = subprocess.run(cmd, cwd=str(wd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "workdir": str(wd),
        "command": " ".join(cmd),
        "model_path": model,
        "note": f"建议测试列表: {test_list}",
    }

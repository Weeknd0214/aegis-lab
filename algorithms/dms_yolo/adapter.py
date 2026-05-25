"""DMS YOLO 引擎：local 研发轨 / platform 平台轨。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

WORKSPACE = Path(__file__).resolve().parents[2]
YOLO_ROOT = WORKSPACE / "algorithms/dms_yolo/code"
DATASET_ROOT = WORKSPACE / "datasets/dms"


def _latest_run(task: str) -> tuple[str | None, str | None]:
    reg = yaml.safe_load((DATASET_ROOT / "datasets.registry.yaml").read_text(encoding="utf-8"))
    typ = reg["tasks"][task]["type"]
    mode_yolo = {"detect": "detect", "pose": "pose", "classify": "classify"}[typ]
    runs = sorted((YOLO_ROOT / "runs" / mode_yolo).glob(f"{task}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        return None, None
    run_dir = runs[0].resolve()
    best = run_dir / "weights" / "best.pt"
    return str(run_dir), str(best) if best.is_file() else None


def train_local(task: str, mode: str = "full", config_overrides: dict | None = None) -> dict[str, Any]:
    """研发轨：train.sh，不 refresh yaml_active，不更新 candidate。"""
    proc = subprocess.run(
        [str(DATASET_ROOT / "scripts" / "train.sh"), task, mode],
        cwd=str(DATASET_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    run_dir, best_weights = _latest_run(task)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "track": "local",
        "command": f"{DATASET_ROOT / 'scripts' / 'train.sh'} {task} {mode}",
        "run_dir": run_dir,
        "best_weights": best_weights,
        "note": "local 轨不写入 train_versions candidate",
    }


def train_platform(task: str, mode: str = "full") -> dict[str, Any]:
    """平台轨：refresh yaml_active + train + 更新 candidate。"""
    subprocess.check_call(
        [sys.executable, str(DATASET_ROOT / "scripts/refresh_yaml.py"), "--task", task],
        cwd=str(DATASET_ROOT),
    )
    proc = subprocess.run(
        [str(DATASET_ROOT / "scripts" / "train.sh"), task, mode],
        cwd=str(DATASET_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)

    run_dir, best_weights = _latest_run(task)
    candidate = None
    if best_weights:
        candidate = best_weights
        versions_path = DATASET_ROOT / "manifests/train_versions.yaml"
        versions = yaml.safe_load(versions_path.read_text(encoding="utf-8"))
        versions[task]["candidate"] = candidate
        versions_path.write_text(yaml.dump(versions, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "track": "platform",
        "command": f"{DATASET_ROOT / 'scripts' / 'train.sh'} {task} {mode}",
        "run_dir": run_dir,
        "best_weights": best_weights,
        "candidate": candidate,
    }


def eval_task(task: str, weights: Path | None = None) -> dict[str, Any]:
    argv = [sys.executable, str(WORKSPACE / "as.py"), "eval", "dms", task, "--save-candidate"]
    if weights:
        argv.extend(["--weights", str(weights)])
    proc = subprocess.run(argv, cwd=str(WORKSPACE), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "weights": str(weights) if weights else None,
        "command": " ".join(argv),
    }


def visualize_task(task: str, weights: Path | None = None) -> dict[str, Any]:
    """复用 eval 流程产出可视化结果。"""
    out = eval_task(task, weights=weights)
    out["note"] = "可视化结果请查看 DMS 评估输出目录与 runs/detect 结果。"
    return out

"""MonoFlex 单目 3D 检测引擎适配（CVPR 2021）。

源码目录: algorithms/monoflex/code/
训练入口: tools/plain_train_net.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE = Path(__file__).resolve().parents[2]
MONOFLEX_ROOT = Path(__file__).resolve().parent / "code"
DEFAULT_CONFIG = MONOFLEX_ROOT / "runs/monoflex.yaml"
DEFAULT_OUTPUT = MONOFLEX_ROOT / "output" / "aegis_train"


def _ensure_code() -> None:
    if not (MONOFLEX_ROOT / "tools/plain_train_net.py").is_file():
        raise FileNotFoundError(
            f"MonoFlex 代码缺失: {MONOFLEX_ROOT}\n"
            "请执行 bash scripts/vendor_monoflex.sh 或从 workspace/BK2/archive/MonoFlex 同步"
        )


def _latest_ckpt(output_dir: Path) -> str | None:
    candidates = sorted(output_dir.rglob("*.pth"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    return str(candidates[0].resolve())


def train_local(
    *,
    config: str | Path | None = None,
    output: str | Path | None = None,
    batch_size: int = 8,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """研发轨：直接调用 MonoFlex 训练脚本。"""
    _ensure_code()
    cfg = Path(config) if config else DEFAULT_CONFIG
    out = Path(output) if output else DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(MONOFLEX_ROOT / "tools/plain_train_net.py"),
        "--batch_size",
        str(batch_size),
        "--config",
        str(cfg),
        "--output",
        str(out),
    ]
    if extra_args:
        cmd.extend(extra_args)
    env = {**os.environ, "PYTHONPATH": str(MONOFLEX_ROOT)}
    proc = subprocess.run(cmd, cwd=str(MONOFLEX_ROOT), capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "track": "local",
        "command": " ".join(cmd),
        "output_dir": str(out),
        "latest_ckpt": _latest_ckpt(out),
    }


def train_platform(**kwargs: Any) -> dict[str, Any]:
    """平台轨：当前与 local 相同；后续可接 adas pack 刷新与 candidate 写入。"""
    out = train_local(**kwargs)
    out["track"] = "platform"
    out["note"] = "MonoFlex 平台轨 candidate 写入待与 adas_moon3d_v1 pack 对齐"
    return out


def eval_checkpoint(
    *,
    ckpt: str | Path,
    config: str | Path | None = None,
    vis: bool = False,
) -> dict[str, Any]:
    """评估指定 checkpoint。"""
    _ensure_code()
    cfg = Path(config) if config else DEFAULT_CONFIG
    cmd = [
        sys.executable,
        str(MONOFLEX_ROOT / "tools/plain_train_net.py"),
        "--config",
        str(cfg),
        "--ckpt",
        str(ckpt),
        "--eval",
    ]
    if vis:
        cmd.append("--vis")
    env = {**os.environ, "PYTHONPATH": str(MONOFLEX_ROOT)}
    proc = subprocess.run(cmd, cwd=str(MONOFLEX_ROOT), capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return {
        "ok": True,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(cmd),
        "ckpt": str(ckpt),
    }


def visualize_task(weights: str | Path | None = None) -> dict[str, Any]:
    """可视化：对最新或指定权重跑 eval --vis。"""
    ckpt = weights
    if ckpt is None:
        ckpt = _latest_ckpt(DEFAULT_OUTPUT)
    if not ckpt:
        raise FileNotFoundError("未找到 checkpoint，请先训练或传入 weights")
    return eval_checkpoint(ckpt=ckpt, vis=True)

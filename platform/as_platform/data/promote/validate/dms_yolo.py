"""DMS YOLO batch validation wrapper."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from as_platform.config import WORKSPACE


def validate_dms_inbox_batch(batch_dir: Path) -> list[str]:
    """Promote 前校验单个 inbox 批次（不要求 pack 目录已存在）。"""
    from as_platform.labeling.batch_stage import batch_has_yolo_labels

    if not batch_dir.is_dir():
        return [f"batch_dir missing: {batch_dir}"]
    if not batch_has_yolo_labels(batch_dir):
        return [f"no YOLO labels under {batch_dir} (先执行 labeling_export)"]
    return []


def validate_dms_task(task: str | None) -> list[str]:
    cmd = [sys.executable, str(WORKSPACE / "scripts" / "validate_dms_tasks.py")]
    if task:
        cmd.extend(["--task", task])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return [proc.stderr or proc.stdout or f"validate_dms_tasks failed exit {proc.returncode}"]
    return []

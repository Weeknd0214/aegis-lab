"""DMS YOLO batch validation wrapper."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from as_platform.config import WORKSPACE


def validate_dms_task(task: str | None) -> list[str]:
    cmd = [sys.executable, str(WORKSPACE / "scripts" / "validate_dms_tasks.py")]
    if task:
        cmd.extend(["--task", task])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return [proc.stderr or proc.stdout or f"validate_dms_tasks failed exit {proc.returncode}"]
    return []

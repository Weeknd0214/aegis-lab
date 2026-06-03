#!/usr/bin/env bash
# ML 自动化 P0：manifest 对齐 + pending 批次 stage 字段可读
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

bash scripts/smoke_manifest_alignment.sh

python3 <<'PY'
import sys
from pathlib import Path

import yaml

root = Path(".")
wf = yaml.safe_load((root / "workflow.registry.yaml").read_text(encoding="utf-8"))
sys.path.insert(0, str(root / "platform"))
from as_platform.data.core import get_pending_report  # noqa: E402

report = get_pending_report(wf)
stages = {b.get("stage") for b in report.get("batches") or []}
required = {"raw_pool", "out_for_labeling", "returned", "labeling_submitted"}
missing = required - stages
if missing:
    print("PENDING_GATE_WARN: no batches in stages", missing, "(ok if inbox empty)")
else:
    print("PENDING_GATE_STAGES_OK", sorted(stages))
print("PENDING_GATE_OK batches=", len(report.get("batches") or []))
PY

echo "OK smoke_pending_gate"

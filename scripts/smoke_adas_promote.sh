#!/usr/bin/env bash
# ADAS cuboid export → 3D fit → promote smoke (val_front6mm_pilot)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BATCH="${AS_SMOKE_BATCH:-val_front6mm_pilot}"
BATCH_DIR="${AS_SMOKE_BATCH_DIR:-$ROOT/../data/送标/adas/inbox/cuboid_7cls/$BATCH}"

export PYTHONPATH="$ROOT/platform:$ROOT"

python3 <<PY
from pathlib import Path
import json
import sys

batch_dir = Path("$BATCH_DIR").resolve()
if not batch_dir.is_dir():
    sys.exit(f"batch dir missing: {batch_dir}")

from as_platform.labeling.export_cuboid_batch import export_batch
from as_platform.labeling.class_map import load_adas_class_names, build_class_map
from as_platform.labeling.fit_cuboid_batch import fit_batch
from as_platform.data.promote.runner import promote_batch

exp = export_batch(batch_dir)
print("export", exp)
assert exp.get("written", 0) > 0, "export wrote 0"

fit = fit_batch(batch_dir)
print("fit", fit)

qfiles = list((batch_dir / "labels/quaternion_json").glob("*.json"))
q = None
for p in qfiles:
    d = json.loads(p.read_text())
    if d.get("detections"):
        q = p
        break
assert q, "no quaternion json with detections"
data = json.loads(q.read_text())
det = data["detections"][0]
names = load_adas_class_names()
assert names[0] == "pedestrian", names
assert det["class_name"] == "car"
assert det["class_id"] == build_class_map(names)["car"], det

result = promote_batch(
    "adas",
    task="cuboid_7cls",
    batch=batch_dir.name,
    pack="adas_moon3d_v1",
    batch_dir=batch_dir,
    skip_validate=False,
    allow_partial_3d=True,
)
print("promote", result)

pack_root = Path("$ROOT/datasets/adas/packs/adas_moon3d_v1")
dest = pack_root / "sources" / batch_dir.name
assert dest.is_dir(), dest
assert (dest / "labels" / "quaternion_json").is_dir()
assert (pack_root / "lists" / "train_stems.txt").is_file()
print("SMOKE_ADAS_PROMOTE_OK")
PY

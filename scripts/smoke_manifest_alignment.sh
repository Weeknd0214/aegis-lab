#!/usr/bin/env bash
# 校验 workflow active_packs、train_versions 与 yaml_active 对齐（ML 自动化 P0）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 <<'PY'
import sys
from pathlib import Path

import yaml

root = Path(".")
wf = yaml.safe_load((root / "workflow.registry.yaml").read_text(encoding="utf-8"))
tv_path = root / "datasets/dms/manifests/train_versions.yaml"
yaml_active = root / "datasets/dms/manifests/yaml_active"
errors: list[str] = []

if not tv_path.is_file():
    errors.append(f"missing {tv_path}")
else:
    tv = yaml.safe_load(tv_path.read_text(encoding="utf-8")) or {}
    for key, meta in tv.items():
        if key in ("schema",):
            continue
        if not isinstance(meta, dict):
            continue
        rel = meta.get("data_yaml")
        if not rel:
            continue
        p = root / "datasets/dms" / rel
        if not p.is_file():
            errors.append(f"train_versions[{key}] data_yaml not found: {p}")

for proj, pcfg in (wf.get("projects") or {}).items():
    for pack in pcfg.get("active_packs") or []:
        if proj == "dms":
            packs_file = root / pcfg.get("packs_registry", "datasets/dms/data_packs.yaml")
            if packs_file.is_file():
                packs = yaml.safe_load(packs_file.read_text(encoding="utf-8")) or {}
                if pack not in (packs.get("packs") or {}):
                    errors.append(f"dms active_pack unknown in data_packs: {pack}")

if errors:
    print("MANIFEST_ALIGNMENT_FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print("MANIFEST_ALIGNMENT_OK")
print("train_versions keys:", len([k for k in yaml.safe_load(tv_path.read_text()) if k != "schema"]))
print("yaml_active files:", len(list(yaml_active.glob("*.yaml"))))
PY

echo "OK smoke_manifest_alignment"

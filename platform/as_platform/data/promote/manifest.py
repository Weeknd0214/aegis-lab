"""Refresh ADAS / DMS pack manifests after promote."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from as_platform.data.core import load_wf, proj_root


def _collect_adas_stems(sources_root: Path) -> list[str]:
    stems: list[str] = []
    if not sources_root.is_dir():
        return stems
    for batch_dir in sorted(sources_root.iterdir()):
        if not batch_dir.is_dir() or batch_dir.name.startswith("."):
            continue
        qdir = batch_dir / "labels" / "quaternion_json"
        if qdir.is_dir():
            for p in sorted(qdir.glob("*.json")):
                stems.append(p.stem)
        else:
            img_root = batch_dir / "images"
            if img_root.is_dir():
                for p in sorted(img_root.rglob("*")):
                    if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                        stems.append(p.stem)
    return sorted(set(stems))


def refresh_adas_lists(wf: dict | None = None, *, pack: str = "adas_moon3d_v1") -> dict[str, Any]:
    wf = wf or load_wf()
    root = proj_root(wf, "adas")
    pack_dir = root / "packs" / pack
    sources = pack_dir / "sources"
    lists_dir = pack_dir / "lists"
    lists_dir.mkdir(parents=True, exist_ok=True)

    stems = _collect_adas_stems(sources)
    val_ratio = 0.1
    reg_path = root / wf["projects"]["adas"]["registry"]
    if reg_path.is_file():
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
        val_ratio = float((reg.get("split") or {}).get("val_ratio", 0.1))

    n_val = max(0, int(len(stems) * val_ratio)) if len(stems) > 1 else 0
    val_stems = stems[:n_val]
    train_stems = stems[n_val:]

    train_path = lists_dir / "train_stems.txt"
    val_path = lists_dir / "val_stems.txt"
    train_path.write_text("\n".join(train_stems) + ("\n" if train_stems else ""), encoding="utf-8")
    val_path.write_text("\n".join(val_stems) + ("\n" if val_stems else ""), encoding="utf-8")

    manifest_dir = pack_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    index_path = manifest_dir / "pack_index.yaml"
    batches = []
    if sources.is_dir():
        for d in sorted(sources.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                batches.append({"batch": d.name, "path": str(d)})
    index = {
        "pack": pack,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "batches": batches,
        "train_stems": len(train_stems),
        "val_stems": len(val_stems),
    }
    index_path.write_text(yaml.dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return {
        "train_list": str(train_path),
        "val_list": str(val_path),
        "pack_index": str(index_path),
        "train_count": len(train_stems),
        "val_count": len(val_stems),
    }


def refresh_dms_yaml(wf: dict | None = None, task: str | None = None) -> None:
    wf = wf or load_wf()
    root = proj_root(wf, "dms")
    import subprocess
    import sys

    cmd = [sys.executable, str(root / "scripts" / "refresh_yaml.py")]
    if task:
        cmd.extend(["--task", task])
    subprocess.check_call(cmd, cwd=str(root))

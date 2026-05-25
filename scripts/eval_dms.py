#!/usr/bin/env python3
"""DMS 标准评估：yolo val → manifests/eval_log.jsonl，可选基线对比。"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

WORKSPACE = Path(__file__).resolve().parents[1]
DATASET = (WORKSPACE / "datasets/dms").resolve()
WF_PATH = WORKSPACE / "workflow.registry.yaml"


def latest_run_weights(yolo_root: Path, mode: str, task: str) -> Path | None:
    base = yolo_root / "runs" / mode
    if not base.is_dir():
        return None
    cands = sorted(base.glob(f"{task}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for run in cands:
        w = run / "weights" / "best.pt"
        if w.is_file():
            return w
    return None


def parse_val_metrics(stdout: str) -> dict:
    metrics = {}
    for key, pat in [
        ("map50", r"mAP50[:\s]+([\d.]+)"),
        ("map50_95", r"mAP50-95[:\s]+([\d.]+)"),
        ("precision", r"Precision[:\s]+([\d.]+)"),
        ("recall", r"Recall[:\s]+([\d.]+)"),
    ]:
        m = re.search(pat, stdout, re.I)
        if m:
            metrics[key] = float(m.group(1))
    return metrics


def append_eval_log(record: dict) -> None:
    log = DATASET / "manifests" / "eval_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    record["ts"] = datetime.now(timezone.utc).isoformat()
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_train_versions() -> dict:
    p = DATASET / "manifests" / "train_versions.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def save_train_versions(data: dict) -> None:
    p = DATASET / "manifests" / "train_versions.yaml"
    p.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--weights", type=Path, help="默认 candidate → current → 最近 runs/*/best.pt")
    ap.add_argument("--save-candidate", action="store_true", help="将权重写入 train_versions candidate")
    args = ap.parse_args()

    reg = yaml.safe_load((DATASET / "datasets.registry.yaml").read_text())
    wf = yaml.safe_load(WF_PATH.read_text())
    versions = load_train_versions()
    task = args.task
    if task not in reg["tasks"]:
        sys.exit(f"未知 task: {task}")

    tcfg = reg["tasks"][task]
    typ = tcfg["type"]
    mode = {"detect": "detect", "pose": "pose", "classify": "classify"}[typ]
    yaml_path = DATASET / "manifests" / "yaml_active" / f"{task}.yaml"
    if not yaml_path.is_file():
        sys.exit(f"缺少 {yaml_path}，请先: python as.py build dms")

    tv = versions.get(task, {})
    weights = args.weights
    if weights is None:
        for key in ("candidate", "current"):
            w = tv.get(key)
            if w and Path(w).is_file():
                weights = Path(w)
                break
    yolo_root = WORKSPACE / "dms/code/yolo26_rknn_ultralytics-main"
    if weights is None:
        weights = latest_run_weights(yolo_root, mode, task)
    if weights is None or not Path(weights).is_file():
        sys.exit("未找到权重，请 --weights 或先 train")

    imgsz = reg["train"][typ]["imgsz"]
    active_packs = wf["projects"]["dms"]["active_packs"]
    name = f"{task}_eval_{datetime.now().strftime('%Y%m%d_%H%M')}"

    cmd = [
        "yolo", mode, "val",
        f"data={yaml_path}",
        f"model={weights}",
        f"imgsz={imgsz}",
        f"project=runs/{mode}",
        f"name={name}",
    ]
    print(" ".join(cmd))
    proc = subprocess.run(cmd, cwd=yolo_root, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    print(out)
    if proc.returncode != 0:
        return proc.returncode

    metrics = parse_val_metrics(out)
    baseline = (wf.get("automation") or {}).get("baseline_metrics", {}).get(task, {})
    record = {
        "task": task,
        "type": typ,
        "weights": str(Path(weights).resolve()),
        "active_packs": active_packs,
        "data_yaml": str(yaml_path),
        "metrics": metrics,
        "baseline": baseline,
        "run_name": name,
    }
    if baseline and metrics.get("map50") is not None and baseline.get("map50") is not None:
        record["delta_map50"] = metrics["map50"] - float(baseline["map50"])

    append_eval_log(record)
    versions[task]["last_eval"] = record
    save_train_versions(versions)

    if args.save_candidate:
        versions[task]["candidate"] = str(Path(weights).resolve())
        save_train_versions(versions)

    print(f"\nmetrics: {metrics}")
    if record.get("delta_map50") is not None:
        print(f"delta mAP50 vs baseline: {record['delta_map50']:+.4f}")

    auto = wf.get("automation") or {}
    min_delta = float(auto.get("min_delta_map50", -1.0))
    if record.get("delta_map50") is not None and record["delta_map50"] < min_delta:
        print(f"FAIL: delta mAP50 < {min_delta}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

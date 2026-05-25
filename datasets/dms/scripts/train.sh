#!/usr/bin/env bash
# train.sh <task> [full|continue]  — 读 datasets.registry.yaml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATASET_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
YOLO26_ROOT="${YOLO26_ROOT:-$(cd "$DATASET_ROOT/../Code/yolo26_rknn_ultralytics-main" 2>/dev/null && pwd || echo "")}"

# 优先使用 dms_yolo26 环境
if [[ -z "${CONDA_DEFAULT_ENV:-}" || "${CONDA_DEFAULT_ENV}" != "dms_yolo26" ]]; then
  if [[ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    conda activate dms_yolo26 2>/dev/null || true
  fi
fi
TASK="${1:?用法: $0 <task> [full|continue]}"
TRAIN_MODE="${2:-full}"

REG="$DATASET_ROOT/datasets.registry.yaml"
YAML="$DATASET_ROOT/manifests/yaml_active/${TASK}.yaml"
VERSIONS="$DATASET_ROOT/manifests/train_versions.yaml"

if [[ ! -f "$YAML" ]]; then
  echo "找不到 yaml: $YAML"
  exit 1
fi

read -r TYPE MODE MODEL EPOCHS LR0 IMGSZ RUN_SUFFIX <<< "$(python3 - <<PY
import yaml
from pathlib import Path
reg = yaml.safe_load(Path("$REG").read_text())
tcfg = reg["tasks"]["$TASK"]
typ = tcfg["type"]
train_mode = "$TRAIN_MODE" if "$TRAIN_MODE" in ("full", "continue") else reg.get("train", {}).get("mode", "full")
t = reg.get("train", {}).get(typ, reg.get("train_defaults", {}).get(typ, {}))
if train_mode == "continue":
    model = t.get("warm_start") or "null"
    epochs = t.get("epochs_continue", t.get("epochs_increment", 50))
    lr0 = t.get("lr0_continue", t.get("lr0", 0.001))
    suffix = "continue"
else:
    model = t.get("model", "yolo26n.pt")
    epochs = t.get("epochs", 100)
    lr0 = t.get("lr0", 0.01)
    suffix = "full"
imgsz = t.get("imgsz", 224 if typ == "classify" else 640)
mode = {"detect": "detect", "pose": "pose", "classify": "classify"}.get(typ, "detect")
print(typ, mode, model, epochs, lr0, imgsz, suffix)
PY
)"

# continue 模式：warm_start 为空则读 train_versions.yaml
if [[ "$TRAIN_MODE" == "continue" && ( "$MODEL" == "null" || "$MODEL" == "None" || -z "$MODEL" ) ]]; then
  MODEL=$(python3 - <<PY 2>/dev/null || true
import yaml
from pathlib import Path
p = Path("$VERSIONS")
if p.is_file():
    v = yaml.safe_load(p.read_text()) or {}
    c = v.get("$TASK", {}).get("current")
    if c: print(c)
PY
)
fi

if [[ "$TRAIN_MODE" == "continue" && ( -z "$MODEL" || "$MODEL" == "null" ) ]]; then
  echo "continue 模式需要 registry.train.<type>.warm_start 或 manifests/train_versions.yaml 中的 current"
  exit 1
fi

RUN_NAME="${TASK}_${RUN_SUFFIX}_$(date +%Y%m%d)"

echo "task=$TASK type=$TYPE yolo_mode=$MODE train_mode=$TRAIN_MODE"
echo "data=$YAML"
echo "model=$MODEL epochs=$EPOCHS lr0=$LR0 imgsz=$IMGSZ name=$RUN_NAME"

if [[ -z "$YOLO26_ROOT" || ! -d "$YOLO26_ROOT" ]]; then
  echo "请设置 YOLO26_ROOT 或安装到 ../Code/yolo26_rknn_ultralytics-main"
  echo "  cd \$YOLO26_ROOT"
  echo "  yolo $MODE train data=$YAML model=$MODEL epochs=$EPOCHS lr0=$LR0 imgsz=$IMGSZ project=runs/${MODE} name=$RUN_NAME"
  exit 0
fi

cd "$YOLO26_ROOT"
yolo "$MODE" train \
  data="$YAML" \
  model="$MODEL" \
  epochs="$EPOCHS" \
  lr0="$LR0" \
  imgsz="$IMGSZ" \
  project="runs/${MODE}" \
  name="$RUN_NAME"

BEST="runs/${MODE}/${RUN_NAME}/weights/best.pt"
echo "完成: $BEST"
echo "请更新 manifests/train_versions.yaml 中 $TASK.current = $BEST"

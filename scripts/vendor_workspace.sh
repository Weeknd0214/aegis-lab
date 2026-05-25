#!/usr/bin/env bash
# 将 workspace 中的算法代码与数据集脚手架复制进 HSAP 仓库（供 Git 提交）
#
# 用法: bash scripts/vendor_workspace.sh
# 大文件（图像、权重、训练 log）不会复制，见各 rsync --exclude
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$(cd "$ROOT/.." && pwd)"
WS="${AS_WORKSPACE_ROOT:-$DATA/workspace}"

if [[ ! -d "$WS" ]]; then
  echo "错误: workspace 不存在: $WS"
  echo "请设置 AS_WORKSPACE_ROOT 或保证 $DATA/workspace 存在"
  exit 1
fi

echo "HSAP: $ROOT"
echo "workspace:     $WS"

RSYNC=(rsync -a --delete --no-group --no-owner --no-perms)

EXCLUDE_COMMON=(
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude '.git/'
  --exclude '.pytest_cache/'
  --exclude 'node_modules/'
  --exclude '*.egg-info/'
)

# ── 移除旧软链，准备实体目录 ──
for p in \
  "$ROOT/algorithms/dms_yolo/code" \
  "$ROOT/algorithms/lane_ufld/code" \
  "$ROOT/datasets/dms" \
  "$ROOT/datasets/lane"
do
  if [[ -L "$p" ]]; then
    rm -f "$p"
  fi
  mkdir -p "$p"
done

echo ""
echo ">>> DMS YOLO 代码 → algorithms/dms_yolo/code/"
"${RSYNC[@]}" "${EXCLUDE_COMMON[@]}" \
  --exclude 'runs/' \
  --exclude '*.pt' \
  --exclude '*.onnx' \
  --exclude '*.rknn' \
  --exclude '*.engine' \
  --exclude 'wandb/' \
  "$WS/DMS/Code/yolo26_rknn_ultralytics-main/" \
  "$ROOT/algorithms/dms_yolo/code/"

echo ">>> Lane UFLD 代码 → algorithms/lane_ufld/code/"
"${RSYNC[@]}" "${EXCLUDE_COMMON[@]}" \
  --exclude 'log/' \
  --exclude 'tmp/' \
  --exclude 'runs/' \
  --exclude '*.pth' \
  --exclude '*.onnx' \
  --exclude 'wandb/' \
  "$WS/LaneDection/Code/" \
  "$ROOT/algorithms/lane_ufld/code/"

echo ">>> DMS 数据集脚手架 → datasets/dms/"
"${RSYNC[@]}" "${EXCLUDE_COMMON[@]}" \
  --exclude 'packs/' \
  --exclude 'inbox/' \
  --exclude 'archive/' \
  --exclude 'sources/' \
  --exclude '*.jpg' --exclude '*.jpeg' --exclude '*.png' \
  --exclude '*.mp4' --exclude '*.avi' \
  "$WS/DMS/DATASET/" \
  "$ROOT/datasets/dms/"

echo ">>> Lane 数据集脚手架 → datasets/lane/"
"${RSYNC[@]}" "${EXCLUDE_COMMON[@]}" \
  --exclude 'archive/' \
  --exclude 'DATASET/' \
  --exclude '*.jpg' --exclude '*.jpeg' --exclude '*.png' \
  --exclude '*.mp4' \
  "$WS/lane/" \
  "$ROOT/datasets/lane/"

# 标记：仓库内为实体文件，非软链
cat > "$ROOT/manifests/repo_layout.json" <<EOF
{
  "layout": "embedded",
  "vendored_at": "$(date -Iseconds)",
  "workspace_source": "$WS",
  "note": "算法代码与数据集脚手架已内嵌；大文件数据请挂载 workspace 或 rsync 到 datasets/"
}
EOF

echo ""
echo "完成。请检查:"
echo "  ls algorithms/dms_yolo/code"
echo "  ls algorithms/lane_ufld/code/UFLD"
echo "  ls datasets/dms/scripts"
echo ""
echo "下一步: git add -A && git status"

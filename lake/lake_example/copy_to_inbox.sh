#!/usr/bin/env bash
# 将 lake_example 样例复制到 HSAP 数据湖 inbox（不覆盖已有批次）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HSAP_ROOT="${HSAP_ROOT:-$(cd "$SCRIPT_DIR/../HSAP" && pwd)}"
SRC="$SCRIPT_DIR/datasets"

echo "HSAP_ROOT=$HSAP_ROOT"
echo "源: $SRC"
echo ""
echo "业务线 → 目标路径:"
echo "  DMS cabin (addw/ddaw/...)     → datasets/dms/inbox/"
echo "  ADAS 2D (adas/inbox/det_7cls) → datasets/adas/inbox/det_7cls/"
echo "  ADAS 3D (adas/inbox/cuboid)   → datasets/adas/inbox/cuboid_7cls/"
echo "  车道线 (lane/inbox)           → datasets/lane/inbox/"
echo ""

rsync -av --ignore-existing "$SRC/dms/inbox/" "$HSAP_ROOT/datasets/dms/inbox/"
rsync -av --ignore-existing "$SRC/adas/inbox/" "$HSAP_ROOT/datasets/adas/inbox/"
rsync -av --ignore-existing "$SRC/lane/inbox/" "$HSAP_ROOT/datasets/lane/inbox/"

echo ""
echo "完成。请到 批次台账 → 扫描数据湖 → 登记。"
echo "索引: $SRC/README.md  |  manifest: $SRC/manifest.yaml"

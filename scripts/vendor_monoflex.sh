#!/usr/bin/env bash
# 从外部 MonoFlex 源同步到 algorithms/monoflex/code（可选；默认源码已在仓内）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${MONOFLEX_SRC:-}"
DEST="$ROOT/algorithms/monoflex/code"

if [[ -z "$SRC" || ! -d "$SRC/tools" ]]; then
  echo "MonoFlex 源码已在仓库内: $DEST"
  echo "若要从其他路径覆盖，请设置: MONOFLEX_SRC=/path/to/MonoFlex bash $0"
  exit 0
fi

mkdir -p "$DEST"
rsync -a --delete \
  --exclude '.git/' \
  --exclude 'output/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.pth' --exclude '*.pt' \
  --exclude '*.egg-info/' \
  --exclude 'wandb/' \
  "$SRC/" "$DEST/"

echo "完成 → $DEST ($(du -sh "$DEST" | cut -f1))"

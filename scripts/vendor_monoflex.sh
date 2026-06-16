#!/usr/bin/env bash
# 将 workspace/BK2/archive/MonoFlex 同步到 algorithms/monoflex/code（不含权重与 output）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$(cd "$ROOT/.." && pwd)"
SRC="${MONOFLEX_SRC:-$DATA/workspace/BK2/archive/MonoFlex}"
DEST="$ROOT/algorithms/monoflex/code"

if [[ ! -d "$SRC/tools" ]]; then
  echo "错误: MonoFlex 源不存在: $SRC"
  exit 1
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

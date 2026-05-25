#!/usr/bin/env bash
# 将 datasets/ 与 algorithms/*/code 软链到外部 workspace（可选，覆盖仓库内嵌副本）
#
# 适用：本地 monorepo 布局 DATA/{HSAP,workspace}
# 克隆单仓库且无外置数据时无需运行本脚本。
#
# 用法:
#   export AS_WORKSPACE_ROOT=/path/to/workspace
#   bash scripts/setup_links.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WS="${AS_WORKSPACE_ROOT:-$(cd "$ROOT/.." && pwd)/workspace}"

if [[ ! -d "$WS/DMS" ]] && [[ ! -d "$WS/LaneDection" ]]; then
  echo "跳过: workspace 无效 ($WS)，继续使用仓库内嵌 algorithms/datasets"
  exit 0
fi

echo "HSAP: $ROOT"
echo "workspace:     $WS"

link_dir() {
  local target="$1" link="$2"
  if [[ -d "$link" && ! -L "$link" ]]; then
    echo "  备份内嵌目录 → ${link}.embedded.bak"
    mv "$link" "${link}.embedded.bak"
  elif [[ -L "$link" ]]; then
    rm -f "$link"
  fi
  mkdir -p "$(dirname "$link")"
  ln -sfn "$target" "$link"
  echo "  $link -> $target"
}

mkdir -p "$WS/Lane" "$ROOT/datasets" "$ROOT/algorithms/dms_yolo" "$ROOT/algorithms/lane_ufld"

# workspace 内 Lane 逻辑入口（可选）
[[ -d "$WS/lane" ]] && ln -sfn "$WS/lane" "$WS/Lane/dataset" 2>/dev/null || true
[[ -d "$WS/LaneDection/Code" ]] && ln -sfn "$WS/LaneDection/Code" "$WS/Lane/code" 2>/dev/null || true

echo ">>> datasets"
link_dir "$WS/DMS/DATASET" "$ROOT/datasets/dms"
link_dir "$WS/lane" "$ROOT/datasets/lane"

echo ">>> algorithms"
link_dir "$WS/DMS/Code/yolo26_rknn_ultralytics-main" "$ROOT/algorithms/dms_yolo/code"
link_dir "$WS/LaneDection/Code" "$ROOT/algorithms/lane_ufld/code"

cat > "$ROOT/manifests/repo_layout.json" <<EOF
{
  "layout": "workspace_symlinks",
  "workspace": "$WS",
  "linked_at": "$(date -Iseconds)"
}
EOF

echo "完成（workspace 软链模式）"

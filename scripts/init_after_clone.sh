#!/usr/bin/env bash
# Git clone 后首次初始化
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[[ -f .env ]] || { cp .env.example .env && echo "已创建 .env"; }
[[ -f manifests/feishu.env ]] || { cp manifests/feishu.env.example manifests/feishu.env && echo "已创建 manifests/feishu.env"; }

if [[ -n "${AS_WORKSPACE_ROOT:-}" ]] && [[ -d "${AS_WORKSPACE_ROOT}/DMS" || -d "${AS_WORKSPACE_ROOT}/LaneDection" ]]; then
  echo "检测到 AS_WORKSPACE_ROOT，切换为 workspace 软链…"
  bash scripts/setup_links.sh
else
  echo "使用仓库内嵌 algorithms/datasets（默认）"
  echo "若有外部 workspace: export AS_WORKSPACE_ROOT=/path/to/workspace && bash scripts/setup_links.sh"
fi

echo ""
echo "Docker 启动: bash scripts/dev_up.sh"
echo "本机启动:   bash scripts/run_local.sh"

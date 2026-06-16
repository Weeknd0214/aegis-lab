#!/usr/bin/env bash
# 一键启动 aegis-lab（平台 + CVAT，单 compose 文件）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 .env"
fi
DEFAULT_WS="$(cd "$ROOT/.." && pwd)/workspace"
if [[ -d "$DEFAULT_WS/DMS" ]] && ! grep -q '^AS_WORKSPACE_ROOT=' .env 2>/dev/null; then
  echo "AS_WORKSPACE_ROOT=$DEFAULT_WS" >> .env
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未安装 Docker"
  exit 1
fi

if [[ ! -f platform/ui-hsap/dist/index.html ]]; then
  echo "==> 首次构建前端静态包"
  bash scripts/build_web.sh
fi

docker compose up -d --build "$@"

echo ""
echo "服务："
echo "  aegis-lab 平台  http://127.0.0.1:${AS_PLATFORM_PORT:-8788}"
echo "  CVAT 标注画布   http://127.0.0.1:${CVAT_PORT:-8081}"
echo "  PostgreSQL      localhost:${AS_DB_PORT:-5433}"
echo "  Redis           localhost:${AS_REDIS_PORT:-6380}"
echo ""
echo "推镜像: bash scripts/docker_push.sh"
echo "拉镜像: docker compose pull && docker compose up -d"

#!/usr/bin/env bash
# 一键启动完整开发环境：postgres + redis + platform + worker
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 .env（默认挂载本仓库；大文件数据可设置 AS_WORKSPACE_ROOT）"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未安装 Docker。Ubuntu: sudo apt install docker.io docker-compose-v2"
  echo "或: https://docs.docker.com/engine/install/"
  exit 1
fi

docker compose up -d --build "$@"

echo ""
echo "服务："
echo "  平台 UI+API  http://127.0.0.1:${AS_PLATFORM_PORT:-8787}"
echo "  PostgreSQL   localhost:${AS_DB_PORT:-5432}"
echo "  Redis        localhost:${AS_REDIS_PORT:-6379}"
echo ""
echo "React 热更新:  docker compose --profile dev up -d web-dev  → :5173"
echo "日志:         docker compose logs -f platform worker"
echo "停止:         docker compose down"

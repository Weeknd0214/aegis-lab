#!/usr/bin/env bash
# 一键启动 HSAP 平台 + 内置 CVAT 标注引擎
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.cvat.yml)

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 .env（默认挂载本仓库；大文件数据可设置 AS_WORKSPACE_ROOT）"
fi
DEFAULT_WS="$(cd "$ROOT/.." && pwd)/workspace"
if [[ -d "$DEFAULT_WS/DMS" ]] && ! grep -q '^AS_WORKSPACE_ROOT=' .env 2>/dev/null; then
  echo "AS_WORKSPACE_ROOT=$DEFAULT_WS" >> .env
  echo "已写入 AS_WORKSPACE_ROOT=$DEFAULT_WS"
fi

if ! grep -q '^CVAT_HOST=' .env 2>/dev/null; then
  echo "CVAT_HOST=http://hsap-cvat-server:8080" >> .env
fi
if ! grep -q '^CVAT_PUBLIC_URL=' .env 2>/dev/null; then
  echo "CVAT_PUBLIC_URL=http://127.0.0.1:8080" >> .env
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "未安装 Docker。Ubuntu: sudo apt install docker.io docker-compose-v2"
  exit 1
fi

docker compose "${COMPOSE_FILES[@]}" up -d --build "$@"

echo ""
echo "服务："
echo "  HSAP 平台     http://127.0.0.1:${AS_PLATFORM_PORT:-8787}"
echo "  CVAT 标注画布 http://127.0.0.1:${CVAT_PORT:-8080}  （由 HSAP 嵌入，无需单独登录）"
echo "  PostgreSQL    localhost:${AS_DB_PORT:-5432}"
echo "  Redis         localhost:${AS_REDIS_PORT:-6379}"
echo ""
echo "React 热更新:  docker compose --profile dev up -d web-dev  → :5173"
echo "日志:         docker compose ${COMPOSE_FILES[*]} logs -f platform worker cvat_server"
echo "停止:         docker compose ${COMPOSE_FILES[*]} down"

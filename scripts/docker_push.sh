#!/usr/bin/env bash
# 构建并推送 aegis-lab 镜像到 GHCR（需 docker login ghcr.io）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REGISTRY="${REGISTRY:-ghcr.io/weeknd0214}"
TAG="${TAG:-latest}"
PLATFORM_IMAGE="${REGISTRY}/aegis-lab-platform:${TAG}"
CVAT_IMAGE="${REGISTRY}/aegis-lab-cvat-server:${TAG}"

echo "==> 构建前端（打进 platform 镜像）"
bash scripts/build_web.sh

echo "==> Platform: ${PLATFORM_IMAGE}"
docker build -t "${PLATFORM_IMAGE}" -f Dockerfile .

echo "==> CVAT server (patches baked): ${CVAT_IMAGE}"
docker build -t "${CVAT_IMAGE}" -f docker/cvat-server/Dockerfile .

if [[ "${PUSH:-1}" == "1" ]]; then
  echo "==> Push to ${REGISTRY}"
  docker push "${PLATFORM_IMAGE}"
  docker push "${CVAT_IMAGE}"
  echo ""
  echo "拉取部署示例:"
  echo "  export AEGIS_IMAGE_TAG=${TAG}"
  echo "  docker compose pull platform worker cvat_server cvat_worker_import cvat_worker_export cvat_worker_annotation"
  echo "  docker compose up -d"
fi

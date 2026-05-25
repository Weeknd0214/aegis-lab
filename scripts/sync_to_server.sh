#!/usr/bin/env bash
# 同步 HSAP 工作区到训练服务器（展开软链）
#
# 用法:
#   ./scripts/sync_to_server.sh USER@HOST:/opt/HSAP
#   ./scripts/sync_to_server.sh USER@HOST:/opt/HSAP --code-only
#   ./scripts/sync_to_server.sh USER@HOST:/opt/HSAP --dms-only
#   ./scripts/sync_to_server.sh USER@HOST:/opt/HSAP --lane-only
set -euo pipefail

REMOTE="${1:?用法: $0 USER@HOST:/path/HSAP [--code-only|--dms-only|--lane-only]}"
shift
MODE="${1:-all}"

AS="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$(cd "$AS/.." && pwd)"
WS="$DATA/workspace"

RSYNC=(rsync -avh --info=progress2 --copy-links)

EXCLUDE=(
  --exclude 'vis_random_*'
  --exclude 'archive/'
  --exclude '__pycache__/'
  --exclude '.git/'
  --exclude 'runs/'
  --exclude 'log/'
  --exclude 'tmp/'
  --exclude 'node_modules/'
  --exclude 'platform/web/dist/'
)

echo "HSAP: $AS"
echo "实体 workspace: $WS"
echo "远程:          $REMOTE"

mkdir_remote() {
  ssh "${REMOTE%%:*}" "mkdir -p '${REMOTE#*:}'"
}

sync_as_meta() {
  mkdir_remote
  "${RSYNC[@]}" \
    "$AS/as.py" \
    "$AS/workflow.registry.yaml" \
    "$AS/README.md" \
    "$AS/requirements.txt" \
    "${REMOTE}/"
  [[ -d "$AS/scripts" ]] && "${RSYNC[@]}" "$AS/scripts/" "${REMOTE}/scripts/"
  [[ -d "$AS/platform/as_platform" ]] && "${RSYNC[@]}" "$AS/platform/as_platform/" "${REMOTE}/platform/as_platform/"
  [[ -d "$AS/algorithms" ]] && "${RSYNC[@]}" --exclude 'code' "$AS/algorithms/" "${REMOTE}/algorithms/"
  [[ -f "$AS/algorithms/registry.yaml" ]] && "${RSYNC[@]}" "$AS/algorithms/registry.yaml" "${REMOTE}/algorithms/"
}

sync_dms_code() {
  "${RSYNC[@]}" "${EXCLUDE[@]}" "$WS/DMS/Code/" "${REMOTE}/algorithms/dms_yolo/code/"
}

sync_dms_data() {
  "${RSYNC[@]}" "${EXCLUDE[@]}" "$WS/DMS/DATASET/" "${REMOTE}/datasets/dms/"
}

sync_lane_data() {
  "${RSYNC[@]}" "${EXCLUDE[@]}" "$WS/lane/" "${REMOTE}/datasets/lane/"
}

sync_lane_code() {
  "${RSYNC[@]}" "${EXCLUDE[@]}" "$WS/LaneDection/Code/" "${REMOTE}/algorithms/lane_ufld/code/"
}

case "$MODE" in
  --code-only) sync_as_meta; sync_dms_code; sync_lane_code ;;
  --dms-only)  sync_as_meta; sync_dms_code; sync_dms_data ;;
  --lane-only) sync_as_meta; sync_lane_data; sync_lane_code ;;
  *)           sync_as_meta; sync_dms_code; sync_dms_data; sync_lane_data; sync_lane_code ;;
esac

echo "完成: cd ${REMOTE#*:} && python as.py status"

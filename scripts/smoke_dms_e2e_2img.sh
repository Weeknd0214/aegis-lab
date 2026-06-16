#!/usr/bin/env bash
# DMS 2 图端到端：setup 落盘+开 Campaign；run 在标完后跑 提交→质检→导出→入库
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/platform:$ROOT"
BASE="${HSAP_API:-http://127.0.0.1:8787}"

BATCH="${DMS_E2E_BATCH:-e2e_2img_20260616}"
TASK="${DMS_E2E_TASK:-addw}"
PACK="${DMS_E2E_PACK:-dms_v1}"
PROJECT="${DMS_E2E_PROJECT:-dms}"
SRC_BATCH="${DMS_E2E_SRC_BATCH:-20260525_pilot}"
MIN_IMAGES="${DMS_E2E_MIN_IMAGES:-2}"
WAIT_LABEL_SEC="${DMS_E2E_WAIT_LABEL_SEC:-0}"

cmd="${1:-setup}"

setup_batch() {
  local batch_dir="/data/hsap/datasets/dms/inbox/${TASK}/${BATCH}"
  local src="/data/hsap/datasets/dms/inbox/${TASK}/${SRC_BATCH}/images/train"
  echo "==> create batch ${batch_dir} (${MIN_IMAGES} images from ${SRC_BATCH})"
  docker exec aegis-lab-platform mkdir -p "${batch_dir}/images/train"
  docker exec aegis-lab-platform bash -c "
    set -e
    src='${src}'
    dst='${batch_dir}/images/train'
    n=0
    for f in \"\$src\"/*.jpg; do
      [ -f \"\$f\" ] || continue
      cp \"\$f\" \"\$dst/\"
      n=\$((n+1))
      [ \"\$n\" -ge ${MIN_IMAGES} ] && break
    done
    echo copied=\$n
    ls -la \"\$dst\"
  "
  docker exec aegis-lab-platform python3 /data/hsap/as.py register-batch dms "${TASK}" "${BATCH}" --stage raw_pool
  docker exec aegis-lab-platform mkdir -p "${batch_dir}/labels/ls_annotations"
}

open_campaign() {
  echo "==> open campaign via API ${BASE}"
  python3 "$ROOT/platform/as_platform/tests/run_dms_e2e_pipeline.py" setup --api "$BASE" \
    --batch "$BATCH" --task "$TASK" --project "$PROJECT" --pack "$PACK" --skip-files
}

case "$cmd" in
  setup)
    setup_batch
    open_campaign
    python3 "$ROOT/platform/as_platform/tests/run_dms_e2e_pipeline.py" info --api "$BASE" \
      --batch "$BATCH" --task "$TASK" --project "$PROJECT"
    echo ""
    echo "请在平台标注 ${MIN_IMAGES} 张图后执行:"
    echo "  bash $0 run"
    echo "  或: DMS_E2E_WAIT_LABEL_SEC=600 bash $0 run-wait"
    ;;
  run|run-wait)
    if [[ "$cmd" == "run-wait" && "$WAIT_LABEL_SEC" == "0" ]]; then
      WAIT_LABEL_SEC=600
    fi
    python3 "$ROOT/platform/as_platform/tests/run_dms_e2e_pipeline.py" run --api "$BASE" \
      --batch "$BATCH" --task "$TASK" --project "$PROJECT" --pack "$PACK" \
      --min-images "$MIN_IMAGES" --wait-label-sec "$WAIT_LABEL_SEC"
    ;;
  info)
    python3 "$ROOT/platform/as_platform/tests/run_dms_e2e_pipeline.py" info --api "$BASE" \
      --batch "$BATCH" --task "$TASK" --project "$PROJECT"
    ;;
  *)
    echo "usage: $0 {setup|run|run-wait|info}"
    exit 1
    ;;
esac

#!/usr/bin/env bash
# 标注 API 冒烟：离线单元测试始终运行；API 部分需 platform 在 :8787（可用 HSAP_API_SKIP=1 跳过）
set -euo pipefail
BASE="${HSAP_API:-http://127.0.0.1:8787}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> offline export_ls_to_yolo unit tests"
python3 "$ROOT/datasets/dms/scripts/test_export_ls_to_yolo.py"

echo "==> offline export_ls_to_lane_gt unit tests"
python3 "$ROOT/datasets/lane/scripts/test_export_ls_to_lane_gt.py"

if [[ "${HSAP_API_SKIP:-0}" == "1" ]]; then
  echo "SKIP API tests (HSAP_API_SKIP=1)"
  echo "OK (offline only)"
  exit 0
fi

echo "==> check platform $BASE"
LOGIN_RESP=$(curl -sS -m 5 -X POST "$BASE/api/v1/auth/dev/login" \
  -H 'Content-Type: application/json' -d '{"name":"smoke"}' 2>&1) || LOGIN_RESP=""

TOKEN=$(printf '%s' "$LOGIN_RESP" | python3 -c "
import sys, json
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(1)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(1)
tok = data.get('access_token')
if not tok:
    print(data.get('detail') or data, file=sys.stderr)
    sys.exit(1)
print(tok)
" 2>/dev/null) || {
  echo "SKIP API tests: platform 未就绪 ($BASE)"
  echo "  启动: cd $ROOT && docker compose up -d platform"
  echo "  或:   bash $ROOT/scripts/run_local.sh"
  echo "  仅跑离线测试可: HSAP_API_SKIP=1 bash $0"
  echo "OK (offline only)"
  exit 0
}

AUTH="Authorization: Bearer $TOKEN"

echo "==> labeling/batches"
curl -sS -H "$AUTH" "$BASE/api/v1/labeling/batches" | python3 -m json.tool | head -40

CID=$(curl -sS -H "$AUTH" "$BASE/api/v1/labeling/batches" | python3 -c "
import sys,json
items=json.load(sys.stdin).get('items',[])
dam=[i for i in items if i.get('task')=='dam' and '0516' in str(i.get('batch',''))]
print(dam[0]['campaign_id'] if dam else (items[0]['campaign_id'] if items else ''))
")

if [[ -z "$CID" ]]; then
  echo "open campaign dam/batch_0516"
  CID=$(curl -sS -X POST -H "$AUTH" -H 'Content-Type: application/json' \
    "$BASE/api/v1/labeling/campaigns/open" \
    -d '{"project":"dms","task":"dam","batch":"batch_0516","mode":"batch_0516","location":"inbox"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")
fi

echo "campaign_id=$CID"
echo "==> bootstrap"
curl -sS -H "$AUTH" "$BASE/api/v1/labeling/campaigns/$CID/bootstrap" | python3 -m json.tool | head -25
echo "==> tasks"
curl -sS -H "$AUTH" "$BASE/api/v1/labeling/campaigns/$CID/tasks?limit=3" | python3 -m json.tool | head -30
echo "==> export"
curl -sS -X POST -H "$AUTH" "$BASE/api/v1/labeling/campaigns/$CID/export" | python3 -m json.tool
echo "OK"

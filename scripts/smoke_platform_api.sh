#!/usr/bin/env bash
# 平台 API 冒烟：labeling + fleet + health（需 platform :8787）
set -euo pipefail
BASE="${HSAP_API:-http://127.0.0.1:8787}"
TOKEN=$(curl -sS -X POST "$BASE/api/v1/auth/dev/login" -H 'Content-Type: application/json' -d '{"name":"smoke"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

echo "==> health"
curl -sS -H "$AUTH" "$BASE/api/v1/health" | python3 -m json.tool

echo "==> labeling/batches (count)"
curl -sS -H "$AUTH" "$BASE/api/v1/labeling/batches" | python3 -c "import sys,json; print('batches', len(json.load(sys.stdin).get('items',[])))"

echo "==> fleet/map-config"
curl -sS -H "$AUTH" "$BASE/api/v1/fleet/map-config" 2>/dev/null | python3 -m json.tool || echo "fleet disabled or 503"

echo "==> fleet/live"
curl -sS -H "$AUTH" "$BASE/api/v1/fleet/live" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('vehicles', len(d.get('vehicles',[])))" || echo "fleet live skip"

CID=$(curl -sS -H "$AUTH" "$BASE/api/v1/labeling/batches" | python3 -c "
import sys,json
items=json.load(sys.stdin).get('items',[])
print(items[0].get('campaign_id','') if items else '')
")
if [[ -n "$CID" ]]; then
  echo "==> export-jobs campaign=$CID"
  curl -sS -H "$AUTH" "$BASE/api/v1/labeling/campaigns/$CID/export-jobs" | python3 -m json.tool | head -15
fi

bash "$(dirname "$0")/smoke_labeling_api.sh"
bash "$(dirname "$0")/smoke_manifest_alignment.sh"
echo "==> pending/gates"
curl -sS -H "$AUTH" "$BASE/api/v1/pending/gates" | python3 -m json.tool
echo "==> labeling/registry-profiles"
curl -sS -H "$AUTH" "$BASE/api/v1/labeling/registry-profiles" | python3 -c "import sys,json; print('profiles', len(json.load(sys.stdin).get('profiles',[])))"
echo "ALL_OK"

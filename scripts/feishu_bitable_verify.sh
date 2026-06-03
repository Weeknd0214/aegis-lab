#!/usr/bin/env bash
# 检查飞书多维表格配置与 HSAP 连通性（需平台已启动、feishu.env 已填 BITABLE_*）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f manifests/feishu.env ]]; then
  set -a
  # shellcheck source=/dev/null
  source manifests/feishu.env
  set +a
fi

BASE="${AS_FRONTEND_URL:-http://127.0.0.1:8787}"
TOKEN="${HSAP_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  if [[ "${AS_DEV_AUTH:-}" =~ ^(1|true|yes)$ ]]; then
    echo "==> 开发登录获取 token"
    TOKEN="$(curl -sS -X POST "$BASE/api/v1/auth/dev/login" \
      -H "Content-Type: application/json" \
      -d '{"name":"feishu-verify"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")"
  fi
fi

if [[ -z "$TOKEN" ]]; then
  echo "请设置 HSAP_TOKEN 或开启 AS_DEV_AUTH 后重试" >&2
  exit 1
fi

echo "==> GET $BASE/api/v1/integrations/feishu/bitable/status"
curl -sS -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/integrations/feishu/bitable/status" | python3 -m json.tool

echo ""
echo "==> GET bitable/tables（查 table_id）"
curl -sS -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/integrations/feishu/bitable/tables" | python3 -m json.tool

echo ""
echo "OK: 若 status.ok=true 且 missing_columns 为空，则列名与飞书表一致。"

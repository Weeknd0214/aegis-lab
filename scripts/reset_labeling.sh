#!/usr/bin/env bash
# 清空送标/标注相关记录，保留平台账号与配置
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 清空 PostgreSQL 送标/标注表"
docker exec hsap-postgres psql -U as_platform -d as_platform <<'SQL'
TRUNCATE labeling_reviews, labeling_export_jobs, labeling_task_assignments, labeling_campaign_access, labeling_campaigns CASCADE;
TRUNCATE dataset_candidates, batch_deliveries CASCADE;
SQL

if curl -sf http://127.0.0.1:8080/api/tasks?page_size=100 -H 'Accept: application/vnd.cvat+json; version=2.0' >/dev/null 2>&1; then
  echo "==> 清空 CVAT Task"
  python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:8080/api/tasks?page_size=100",
    headers={"Accept": "application/vnd.cvat+json; version=2.0"},
)
with urllib.request.urlopen(req) as r:
    data = json.load(r)
for t in data.get("results", []):
    tid = t["id"]
    del_req = urllib.request.Request(
        f"http://127.0.0.1:8080/api/tasks/{tid}",
        method="DELETE",
        headers={"Accept": "application/vnd.cvat+json; version=2.0"},
    )
    try:
        urllib.request.urlopen(del_req)
        print(f"  deleted CVAT task #{tid} {t.get('name')}")
    except Exception as e:
        print(f"  skip task #{tid}: {e}")
PY
fi

echo "==> 完成。数据湖目录: ${AS_DATA_LAKE:-$ROOT/../data/送标}"

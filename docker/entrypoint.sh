#!/bin/bash
set -euo pipefail
cd /data/hsap

if [[ -d /data/workspace/DMS || -d /data/workspace/LaneDection ]]; then
  echo "[entrypoint] 检测到外部 workspace，重建软链…"
  bash scripts/setup_links.sh || true
else
  echo "[entrypoint] 使用仓库内嵌 algorithms/datasets"
fi

python scripts/wait_for_db.py
python scripts/db_migrate_from_sqlite.py 2>/dev/null || true

exec "$@"

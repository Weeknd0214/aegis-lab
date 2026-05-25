#!/usr/bin/env bash
# 本机直跑（不用 Docker 跑 platform/worker）
# 依赖: pip install -r requirements.txt
# PostgreSQL 可选；不可用时自动回退 SQLite
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/platform${PYTHONPATH:+:$PYTHONPATH}"

if [[ -f "$ROOT/manifests/feishu.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/manifests/feishu.env"
  set +a
fi

export AS_JOB_EXECUTOR="${AS_JOB_EXECUTOR:-thread}"

cd "$ROOT"
bash scripts/setup_links.sh 2>/dev/null || true

if ! python - <<'PY' 2>/dev/null; then
from as_platform.db.engine import check_connection
raise SystemExit(0 if check_connection() else 1)
PY
  export AS_DATABASE_URL="${AS_DATABASE_URL:-sqlite:///${ROOT}/manifests/platform.db}"
  echo "PostgreSQL 不可用，使用 SQLite: ${AS_DATABASE_URL}"
fi

python scripts/wait_for_db.py
python scripts/db_migrate_from_sqlite.py 2>/dev/null || true

echo ""
echo "启动平台 API: http://127.0.0.1:${AS_PLATFORM_PORT:-8787}"
echo "开发登录: AS_DEV_AUTH=true 时在登录页点「开发登录」"
echo ""

exec python -m as_platform.api.server --host "${AS_PLATFORM_HOST:-127.0.0.1}" --port "${AS_PLATFORM_PORT:-8787}" "$@"

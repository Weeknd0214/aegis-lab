"""华胥卡车主动安全（AEB）平台根配置。"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

AS_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE = AS_ROOT

PLATFORM_DIR = AS_ROOT / "platform"
PLATFORM_WEB = PLATFORM_DIR / "web" / "dist"
ALGORITHMS_DIR = AS_ROOT / "algorithms"
DATASETS_DIR = AS_ROOT / "datasets"
ALGORITHMS_REGISTRY = ALGORITHMS_DIR / "registry.yaml"

MANIFESTS = AS_ROOT / "manifests"
JOB_LOG = MANIFESTS / "job_log.jsonl"
APPROVAL_QUEUE = MANIFESTS / "approval_queue.jsonl"
TRACE_LOG = MANIFESTS / "trace_log.jsonl"
GRAPH_STATE_DIR = MANIFESTS / "graph_state"
ENGINES_REGISTRY = ALGORITHMS_REGISTRY
SQLITE_LEGACY_PATH = MANIFESTS / "platform.db"

# ── 数据库（默认 PostgreSQL）──
DB_HOST = os.environ.get("AS_DB_HOST", "127.0.0.1")
DB_PORT = os.environ.get("AS_DB_PORT", "5432")
DB_USER = os.environ.get("AS_DB_USER", "as_platform")
DB_PASSWORD = os.environ.get("AS_DB_PASSWORD", "as_platform")
DB_NAME = os.environ.get("AS_DB_NAME", "as_platform")


def build_database_url() -> str:
    explicit = os.environ.get("AS_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    pwd = quote_plus(DB_PASSWORD)
    return f"postgresql+psycopg2://{DB_USER}:{pwd}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


DATABASE_URL = build_database_url()
IS_POSTGRES = DATABASE_URL.startswith("postgresql")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# ── Redis（Job 队列 / 事件，docker compose 默认 redis:6379）──
REDIS_URL = os.environ.get("AS_REDIS_URL", "redis://127.0.0.1:6379/0")
JOB_QUEUE_KEY = os.environ.get("AS_JOB_QUEUE_KEY", "as:job_queue")
# thread: API 进程内执行（本机 run_local.sh）| worker: 推 Redis，由 worker 容器/脚本消费
JOB_EXECUTOR = os.environ.get("AS_JOB_EXECUTOR", "thread")

# ── 认证 / 飞书 ──
JWT_SECRET = os.environ.get("AS_JWT_SECRET", "change-me-in-production")
JWT_EXPIRE_HOURS = int(os.environ.get("AS_JWT_EXPIRE_HOURS", "168"))
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_REDIRECT_URI = os.environ.get(
    "FEISHU_REDIRECT_URI",
    "http://127.0.0.1:8787/api/v1/auth/feishu/callback",
)
FRONTEND_URL = os.environ.get("AS_FRONTEND_URL", "http://127.0.0.1:8787")
DEV_AUTH_ENABLED = os.environ.get("AS_DEV_AUTH", "").lower() in ("1", "true", "yes")
FEISHU_ADMIN_OPEN_IDS = {
    x.strip() for x in os.environ.get("FEISHU_ADMIN_OPEN_IDS", "").split(",") if x.strip()
}
FEISHU_ADMIN_DEPARTMENT_IDS = {
    x.strip() for x in os.environ.get("FEISHU_ADMIN_DEPARTMENT_IDS", "").split(",") if x.strip()
}

# ── 功能开关 ──
# 车道线 catalog 质检统计（mask 抽样，较慢）；暂时默认关闭
LANE_DATA_VIZ_ENABLED = os.environ.get("AS_LANE_DATA_VIZ", "").lower() in ("1", "true", "yes")

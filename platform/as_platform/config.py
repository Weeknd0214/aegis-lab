"""华胥卡车主动安全（AEB）平台根配置。"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

AS_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE = AS_ROOT


def resolve_workspace_root() -> Path | None:
    """外部 workspace（DMS/Lane 大文件）；Docker 内通常为 /data/workspace。"""
    candidates: list[Path] = []
    explicit = os.environ.get("AS_WORKSPACE_ROOT", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend((Path("/data/workspace"), AS_ROOT.parent / "workspace"))
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved.is_dir() and (resolved / "DMS").is_dir():
            return resolved
    return None


WORKSPACE_ROOT = resolve_workspace_root()

PLATFORM_DIR = AS_ROOT / "platform"
# Label Studio 工程构建产物（scripts/build_hsap_ls_ui.sh）
PLATFORM_WEB = PLATFORM_DIR / "ui-hsap" / "dist"
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
FORCE_DEV_AUTH = os.environ.get("AS_FORCE_DEV_AUTH", "").lower() in ("1", "true", "yes")
FEISHU_ADMIN_OPEN_IDS = {
    x.strip() for x in os.environ.get("FEISHU_ADMIN_OPEN_IDS", "").split(",") if x.strip()
}
FEISHU_ADMIN_DEPARTMENT_IDS = {
    x.strip() for x in os.environ.get("FEISHU_ADMIN_DEPARTMENT_IDS", "").split(",") if x.strip()
}

# ── 飞书多维表格（内网出站同步）──
FEISHU_BITABLE_APP_TOKEN = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
# 表在知识库/wiki 内时：填 wiki 链接里 /wiki/ 后节点 ID；HSAP 会调 API 解析为 Basc obj_token
FEISHU_BITABLE_WIKI_NODE_TOKEN = os.environ.get("FEISHU_BITABLE_WIKI_NODE_TOKEN", "").strip()
FEISHU_BITABLE_TABLE_ID = os.environ.get("FEISHU_BITABLE_TABLE_ID", "").strip()
FEISHU_LABELING_CHAT_ID = os.environ.get("FEISHU_LABELING_CHAT_ID", "").strip()
FEISHU_BITABLE_SYNC_ENABLED = os.environ.get("FEISHU_BITABLE_SYNC_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)
FEISHU_BITABLE_SYNC_INTERVAL_SEC = max(30, int(os.environ.get("FEISHU_BITABLE_SYNC_INTERVAL_SEC", "120")))
FEISHU_BITABLE_AUTO_INGEST = os.environ.get("FEISHU_BITABLE_AUTO_INGEST", "").lower() in (
    "1",
    "true",
    "yes",
)
FEISHU_BITABLE_WEBHOOK_ENABLED = os.environ.get("FEISHU_BITABLE_WEBHOOK_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)

# 中文列名（与 FEISHU_BITABLE_OPS.md 一致，可用环境变量覆盖）
def _field(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


FEISHU_BITABLE_FIELDS: dict[str, str] = {
    "delivery_id": _field("FEISHU_BITABLE_FIELD_DELIVERY_ID", "批次编号"),
    "project": _field("FEISHU_BITABLE_FIELD_PROJECT", "项目"),
    "task": _field("FEISHU_BITABLE_FIELD_TASK", "任务"),
    "mode": _field("FEISHU_BITABLE_FIELD_MODE", "子模式"),
    "batch_name": _field("FEISHU_BITABLE_FIELD_BATCH_NAME", "批次名"),
    "data_path": _field("FEISHU_BITABLE_FIELD_DATA_PATH", "数据路径"),
    "status": _field("FEISHU_BITABLE_FIELD_STATUS", "状态"),
    "candidate_id": _field("FEISHU_BITABLE_FIELD_CANDIDATE_ID", "候选ID"),
    "campaign_id": _field("FEISHU_BITABLE_FIELD_CAMPAIGN_ID", "活动ID"),
    "inbox_path": _field("FEISHU_BITABLE_FIELD_INBOX_PATH", "Inbox路径"),
    "progress": _field("FEISHU_BITABLE_FIELD_PROGRESS", "HSAP进度"),
    "hsap_link": _field("FEISHU_BITABLE_FIELD_HSAP_LINK", "HSAP链接"),
    "error_message": _field("FEISHU_BITABLE_FIELD_ERROR_MESSAGE", "失败原因"),
    "last_sync": _field("FEISHU_BITABLE_FIELD_LAST_SYNC", "最后同步"),
    "record_id": _field("FEISHU_BITABLE_FIELD_RECORD_ID", "记录ID"),
}

# HSAP stage → 飞书表状态
FEISHU_STATUS_FROM_STAGE: dict[str, str] = {
    "raw_pool": "待送标",
    "out_for_labeling": "标注中",
    "returned": "待入库",
    "ingested": "已入库",
    "labeling_submitted": "标注中",
}

# ── 功能开关 ──
# 车道线 catalog 质检统计（mask 抽样，较慢）；暂时默认关闭
LANE_DATA_VIZ_ENABLED = os.environ.get("AS_LANE_DATA_VIZ", "").lower() in ("1", "true", "yes")

# ── 车队地图 / T-Box ──
FLEET_MAP_ENABLED = os.environ.get("AS_FLEET_MAP_ENABLED", "1").lower() in ("1", "true", "yes")
FLEET_MOCK_SEED = os.environ.get("AS_FLEET_MOCK_SEED", "1").lower() in ("1", "true", "yes")
FLEET_MOCK_SIMULATE = os.environ.get("AS_FLEET_MOCK_SIMULATE", "1").lower() in ("1", "true", "yes")
FLEET_SIM_INTERVAL_SEC = int(os.environ.get("AS_FLEET_SIM_INTERVAL_SEC", "8"))
AMAP_KEY = os.environ.get("AS_AMAP_KEY", "").strip()
# 车队地图瓦片：gaode（国内默认）| osm
MAP_TILE_PROVIDER = os.environ.get("AS_MAP_TILE_PROVIDER", "gaode").strip().lower() or "gaode"
TBOX_INGEST_TOKEN = os.environ.get("AS_TBOX_INGEST_TOKEN", "hsap-demo-tbox-token").strip()

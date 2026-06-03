# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**HSAP** (Huaxu Sentinel Active Safety Platform / 华胥 Sentinel 主动安全平台) is a truck active safety algorithm iteration platform covering DMS (Driver Monitoring), Lane detection, and ADAS perception tasks.

It is NOT a training framework — it is a **platform** that orchestrates collaboration workflows: data ingestion → labeling → audit → training → promotion, with full traceability and governance.

## Architecture: Three-Layer Decoupling

The top-level directory is strictly separated into three layers:

```
HSAP/
├── platform/          # Orchestration layer (API, auth, audit, jobs, web UI)
├── algorithms/        # Algorithm code layer (YOLO, UFLD adapters + registries)
├── datasets/          # Data layer (packs, inbox, sources, labeling configs)
├── scripts/           # Operational scripts (init, smoke tests, sync, worker)
├── docs/              # Documentation (20+ md files covering all aspects)
├── lake/              # Data lake staging area
├── reports/           # Reports, CSVs, figures
├── manifests/         # Runtime configs (feishu.env, DB, job logs, catalog cache)
├── as.py              # CLI entry point for workflow commands
├── workflow.registry.yaml  # Central registry: projects, packs, automation rules
├── docker-compose.yml      # PostgreSQL + Redis + platform + worker + optional minio
├── Dockerfile              # Python 3.11-slim, FastAPI on port 8787
└── Makefile                # up/down/dev/logs/build/ps/health shortcuts
```

### Layer Responsibilities

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| `platform/as_platform/` | FastAPI backend: API routes, auth (Feishu SSO + JWT), job queue, labeling service, data lake ingest, fleet map, DB models | `api/server.py`, `config.py`, `sdk.py` |
| `algorithms/` | Algorithm adapters: DMS YOLO and Lane UFLD, each with an `adapter.py` and metadata | `registry.yaml` for algorithm registration |
| `datasets/` | Dataset scaffolds: DMS packs (YAML registry), Lane packs (JSON registry), labeling configs | `dms/data_packs.yaml`, `lane/datasets_registry.json` |

## Key Design Decisions

### 1. Platform orchestrates, does NOT implement training
Training is routed through adapters (`algorithms/*/adapter.py`) and the job runner (`platform/as_platform/jobs/runner.py`). Adding a new task type only requires a new adapter + registry entry.

### 2. Audit-first governance
All write operations (build/train/promote/register) go through an audit queue by default. This ensures every model-affecting action is reviewable and traceable.

### 3. Dual execution modes
- **`thread`**: In-process thread execution (local dev, no Redis needed). Set via `AS_JOB_EXECUTOR=thread`.
- **`worker`**: Redis-backed async execution (Docker/production). Set via `AS_JOB_EXECUTOR=worker`. Worker runs `scripts/worker.py`.

### 4. Database flexibility
- Docker: PostgreSQL 16 (auto-configured)
- Local: Auto-falls back to SQLite (`manifests/platform.db`) when PostgreSQL is unavailable

### 5. Authentication
- Feishu (飞书) OAuth2 SSO with JWT tokens
- Dev mode: `AS_DEV_AUTH=true` bypasses Feishu login
- RBAC roles: `admin`, `reviewer`, `engineer`, `labeler`, `viewer`

## Platform Subsystems (`platform/as_platform/`)

```
as_platform/
├── api/           # FastAPI routes: auth, labeling, delivery, fleet, Feishu callbacks
├── auth/          # Feishu OAuth, JWT tokens, user management, RBAC deps
├── db/            # SQLAlchemy engine, models (User, Job, Campaign, etc.), init
├── data/          # Data lake core: ingest pipelines (DMS COCO/YOLO, Lane lines/mask), batch staging, catalog cache
│   └── ingest/    # Ingest adapters: dms_coco, dms_yolo, dms_inbox_raw, lane_lines, lane_mask
├── labeling/      # Labeling service: annotate, batch staging, vendor import, scope, progress, locks
├── audit/         # Audit queue and preview logic
├── jobs/          # Job queue (Redis List or in-memory), runner, Feishu Bitable sync
├── deliveries/    # Delivery/model handoff service
├── fleet/         # Fleet map: GPS tracking, T-Box ingest, mock data seeding
├── training/      # Training service orchestration
├── agents/        # Agent graphs: ingest_flow, labeling_flow, train_promote_flow
│   └── graphs/    # Workflow graph definitions
├── integrations/  # Third-party: Feishu Bitable, Feishu notify, delivery ingest
├── redis/         # Redis pub/sub bus
├── config.py      # Central config from env vars (AS_* prefix)
└── sdk.py         # Python SDK for platform operations
```

## CLI Usage (`as.py`)

```bash
python as.py status                    # Show workspace and active packs
python as.py pending                   # Show pending audit items
python as.py add dms dam --src ...     # Register a DMS batch
python as.py build dms dam             # Build dataset from active packs
python as.py train dms dam --track local     # Train locally
python as.py train dms dam --track platform  # Train via platform (requires audit)
```

## Workflow Registry (`workflow.registry.yaml`)

Central configuration for:
- **Projects**: `dms` (DMS YOLO) and `lane` (Lane UFLD), each with root paths, registries, active packs
- **Platform settings**: batch metadata schema, drop zones for inbox/sources, training tracks, agent graphs
- **Automation rules**: eval-before-promote requirement, minimum delta thresholds, baseline metrics

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| platform | 8787 | FastAPI + static web UI |
| postgres | 5432 (host mapped to 5433) | PostgreSQL 16 |
| redis | 6379 (host mapped to 6380) | Redis 7 |
| worker | - | Async job executor (same image, different command) |
| minio | 9000/9001 | Optional S3-compatible staging (profile: minio) |

## Build & Run Commands

```bash
# Quick start (Docker)
bash scripts/init_after_clone.sh   # Generate .env / feishu.env
bash scripts/dev_up.sh             # Or: make up

# Local dev (no Docker for platform)
pip install -r requirements.txt
bash scripts/run_local.sh

# Infrastructure only (Docker) + local platform
docker compose up -d postgres redis
bash scripts/run_local.sh

# Utilities
make logs      # platform + worker logs
make down      # stop all
make dev       # with Vite hot reload on :5173
make health    # check API health
```

## Key Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AS_PLATFORM_PORT` | 8787 | Platform API port |
| `AS_DB_HOST/PORT/USER/PASSWORD/NAME` | - | PostgreSQL connection |
| `AS_REDIS_URL` | - | Redis connection URL |
| `AS_JOB_EXECUTOR` | `thread` | `thread` or `worker` |
| `AS_DEV_AUTH` | `false` | Bypass Feishu auth in dev |
| `AS_JWT_SECRET` | - | JWT signing secret |
| `AS_WORKSPACE_ROOT` | - | External workspace path for large files |
| `AS_FLEET_MAP_ENABLED` | `1` | Enable fleet map APIs |
| `AS_FLEET_MOCK_SEED` | `1` | Seed demo vehicles on first start |

## Important Conventions

1. **Never commit**: `.env`, `feishu.env`, `node_modules`, `*.pt` (model weights), images/videos
2. **Python path**: Platform code runs with `PYTHONPATH=platform` from repo root
3. **Package name**: The Python package is `as_platform` (historical name preserved)
4. **Web UI**: React/Vite frontend sources are external (in workspace), built via `scripts/build_hsap_ls_ui.sh`
5. **Large files**: Images, videos, model weights live in external workspace, mounted at `/data/workspace` in Docker

## Documentation Index

Key docs in `docs/`:
- `DEVELOPMENT_GUIDE.md` — Architecture, conventions, design decisions
- `DEVELOPMENT_ROADMAP.md` — Q2 2026 roadmap with phased milestones
- `DATA_LAKE_CHECKLIST.md` — Data lake operations checklist
- `LABELING_SOP.md` — Labeling standard operating procedure
- `FLEET_MAP.md` — Fleet map / T-Box GPS tracking
- `FEISHU_BITABLE_OPS.md` — Feishu Bitable integration operations
- `BATCH_DELIVERY_OPS.md` — Batch delivery operations
- `LANE_LABELING_PLAN.md` — Lane labeling plan
- `MINIO_STAGING.md` — S3-compatible staging setup
- `PILOT_BATCH.md` — Pilot batch procedures
- `GIT_PUSH.md` — Git push checklist

## Module Navigation (4-Module Architecture)

The frontend (`platform/web/`) is organized into 4 decoupled modules, each with its own tab sub-navigation:

| Module | Route Prefix | API Prefix | Sub-pages |
|--------|-------------|-----------|-----------|
| **数据送标** (Labeling) | `/labeling/*` | `/api/v1/labeling/*` | 数据上载、送标工作台、标注进度、导出与入库、批次台账、数据目录 |
| **模型管理** (Models) | `/models/*` | `/api/v1/models/*` | 模型概览、训练提交、训练记录、评估管理、模型晋级 |
| **车队管理** (Fleet) | `/fleet/*` | `/api/v1/fleet/*` | 车队总览、车辆管理、实时地图、行程记录、T-Box配置 |
| **系统管理** (System) | `/system/*` | `/api/v1/system/*` | 审核队列、任务监控、执行日志、用户管理 |

**Key files:**
- `platform/web/src/app/Sidebar.tsx` — Collapsible accordion sidebar with permission-gated module groups
- `platform/web/src/app/MainShell.tsx` — Main layout with sidebar + content area + legacy redirects
- `platform/web/src/modules/{labeling,models,fleet,system}/*Shell.tsx` — Module shells with tab sub-navigation
- `platform/as_platform/api/models_routes.py` — `/api/v1/models/*` (model lifecycle APIs)
- `platform/as_platform/api/system_routes.py` — `/api/v1/system/*` (audit, jobs, traces, users APIs)

**Legacy route redirects** (old → new):
- `/deliveries` → `/labeling/deliveries`
- `/catalog` → `/labeling/catalog`
- `/audit` → `/system/audit`
- `/jobs` → `/system/jobs`
- `/training` → `/models/training/records`
- `/labeling/ml` → `/models/overview`

## Technology Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0, Uvicorn
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS (`platform/web/`)
- **Database**: PostgreSQL 16 (production), SQLite (local fallback)
- **Queue**: Redis (List-based job queue + Pub/Sub)
- **Auth**: Feishu OAuth2 + JWT (python-jose)
- **Container**: Docker Compose v2
- **Algorithms**: YOLOv6 (DMS), UFLD (Lane detection)

## 开发计划 — 缺失功能 Todo

### P0 · 首页仪表盘 (1天)
- [ ] 新建 `/` 路由仪表盘页，替代当前直接跳转批次台账
- [ ] 数据流水线 KPI 卡片：各阶段批次数（待送标/标中/待入库/已入库）
- [ ] 模型健康卡片：最新 mAP、训练中任务数、生产模型版本
- [ ] 审核待办卡片：pending 审核数、今日处理量
- [ ] 车队实时卡片：在线车辆数、活跃行程数
- [ ] 最近活动时间线（最近登记/审核/训练事件）

### P0 · 飞书审核通知 (0.5天)
- [ ] 审核提交时 → 通知审核员群："{user} 提交了 {action}，请审核"
- [ ] 审核通过/驳回时 → 通知提审人："你的 {action} 已{通过/驳回}"
- [ ] 复用已有 `integrations/feishu_notify.py`，接入 `audit/queue.py`
- [ ] 环境变量 `FEISHU_LABELING_CHAT_ID` 控制通知目标群

### P1 · 入库基础质检 (1天)
- [ ] 扫描入库时增加基础质量检测：
  - 图片可读性（损坏/全黑/全白检测）
  - 分辨率分布（中位数/最小/最大）
  - 标注文件格式正确性（YOLO 格式校验）
  - 标注框越界/零宽高检测
- [ ] 质检结果在扫描面板展示（通过/警告/拒绝）
- [ ] 拒绝的批次不允许登记，需人工处理

### P1 · 操作审计日志 (0.5天) — 详细设计

#### DB 设计
- [ ] A1. 新增 `OperationLog` 表 (SQLAlchemy model)
  - `id` (int, PK, auto)
  - `timestamp` (datetime, 操作时间)
  - `user_id` (int, FK → users.id, nullable, 操作人)
  - `user_name` (str, 操作人姓名冗余)
  - `category` (str, 操作分类: auth/data/labeling/audit/training/system)
  - `action` (str, 具体操作: login/logout/register_batch/open_campaign/submit_approval/approve/reject/set_roles/create_snapshot/build_dms/train_dms 等)
  - `target_type` (str, 操作对象类型: user/batch/campaign/approval/job/snapshot/role)
  - `target_id` (str, 操作对象 ID)
  - `summary` (str, 一行摘要，如 "登记批次 ddaw/20260601_pilot → raw_pool")
  - `detail_json` (text, 完整上下文 JSON，可选)
  - `ip_address` (str, 请求来源 IP，可选)
- [ ] A2. 自动建表 (`Base.metadata.create_all` + `_ensure_*_columns`)
- [ ] A3. 定期清理：保留 90 天，超过的自动归档/删除

#### 后端埋点
- [ ] B1. 新增 `audit_log.py` 工具模块，提供 `log_op(db, **kwargs)` 便捷函数
- [ ] B2. 在以下关键操作处插入日志记录：

| 分类 | 操作 | 文件位置 |
|------|------|---------|
| auth | login (dev/feishu) | `auth_routes.py` |
| auth | logout | (前端触发，可选) |
| data | register_batch | `server.py` api_register_batch |
| data | scan_inbox | `server.py` (只记录登记动作) |
| labeling | open_campaign | `labeling_routes.py` |
| labeling | submit_campaign | `labeling_routes.py` |
| labeling | labeling_export | `labeling_routes.py` |
| labeling | import_vendor | `labeling_routes.py` |
| audit | submit_approval | `queue.py` |
| audit | approve | `queue.py` |
| audit | reject | `queue.py` |
| training | create_training | `server.py` / `models_routes.py` |
| system | set_user_roles | `auth_routes.py` |
| system | sync_feishu_users | `system_routes.py` |
| data | create_snapshot | `models_routes.py` |
| delivery | create/submit/delete | `delivery_routes.py` |

- [ ] B3. 所有日志记录使用 `threading.Thread(daemon=True)` 异步写入，不阻塞主流程

#### 后端 API
- [ ] C1. `GET /api/v1/system/audit-log` — 查询日志列表
  - 参数: `user_id`, `category`, `action`, `target_type`, `search`(模糊搜索 summary), `offset`, `limit`
  - 返回: `{items: [...], total: N}`
  - 权限: `admin:users` 或 `*`
- [ ] C2. `GET /api/v1/system/audit-log/stats` — 统计摘要
  - 返回: `{today_count, top_users, top_actions, by_category}`

#### 前端页面
- [ ] D1. 系统管理 → 新增"操作日志"Tab
  - 时间线列表视图（倒序），每行显示：时间、用户头像+姓名、分类Badge、操作摘要
  - 筛选栏：按用户、分类、操作类型、时间范围
  - 点击展开查看 detail JSON
  - 分页
- [ ] D2. 仪表盘增加"最近操作"卡片（可选，后做）

### P2 · 标注质量抽检 (1.5天)
- [ ] 标注提交后随机抽取 N 张（可配置比例），进入抽检队列
- [ ] 抽检页面：并排显示图片+标注框，通过/不通过
- [ ] 不通过 → 退回标注员重标
- [ ] 统计抽检通过率、各标注员准确率

### P2 · 模型预标（需要模型）(2天)
- [ ] 选已有模型 → 对新批次跑推理 → 生成预标注
- [ ] 标注员在预标基础上修正，而非从零开始
- [ ] 记录预标模型版本，关联到后续训练

### P3 · 模型部署追踪（需要生产环境）
- [ ] 模型版本状态：experiment → candidate → production → retired
- [ ] 部署历史：何时上线、运行多久、何时下线
- [ ] 线上推理效果监控（回传误检/漏检统计）

### P3 · 采集任务管理（需要车队运营）
- [ ] 创建采集任务：指定场景/路线/时间段
- [ ] 关联车队车辆：指派车辆执行采集
- [ ] 数据回传状态追踪：已采集/已传输/已入库

---

## 当前完成状态

| 模块 | 页面 | 状态 |
|------|------|------|
| 数据送标 | 送标工作台 (扫描入库) | ✅ |
| 数据送标 | 标注进度 (Campaigns) | ✅ |
| 数据送标 | 导出与入库 (供应商回传) | ✅ |
| 数据送标 | 批次台账 (Deliveries) | ✅ |
| 数据送标 | 数据目录 (可视化) | ✅ |
| 模型管理 | 模型概览 (KPI卡片) | ✅ |
| 模型管理 | 数据集版本 (自动快照+diff) | ✅ |
| 模型管理 | 训练提交 (表单校验) | ✅ |
| 模型管理 | 训练记录 (分页+展开详情) | ✅ |
| 模型管理 | 评估管理 (mAP对比图) | ✅ |
| 模型管理 | 模型晋级 (版本选择+历史) | ✅ |
| 车队管理 | 总览/车辆/地图/行程/T-Box | ✅ |
| 系统管理 | 审核队列 (批量操作+驳回分类) | ✅ |
| 系统管理 | 任务监控 (自动刷新) | ✅ |
| 系统管理 | 执行日志 (Trace查看) | ✅ |
| 系统管理 | 用户管理 (飞书信息+分页) | ✅ |
| 🆕 P0 | 首页仪表盘 | ❌ |
| 🆕 P0 | 飞书审核通知 | ❌ |
| 🆕 P1 | 入库基础质检 | ❌ |
| 🆕 P1 | 操作审计日志 | ❌ |

---

## 新增架构：世界模型仿真 + 视频预处理管线

### 一、整体数据闭环（完整架构）

```
                        ┌──────────────────────────────┐
                        │      T-Box / 采集车 GPS       │
                        │  多帧视频流 (连续帧)           │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────┐
│              视频预处理管线 (Preprocess Pipeline)              │
│                                                              │
│  ① 去噪 (Denoise)    ② 去重 (Dedup)    ③ 异常过滤 (Anomaly) │
│  光流/像素级去噪       SSIM/感知哈希      全黑/模糊/过曝检测   │
│       │                    │                    │            │
│       └────────────────────┴────────────────────┘            │
│                            │                                  │
│                      ④ 关键帧提取                              │
│                   场景切换/间隔采样                             │
│                            │                                  │
│                      ⑤ 质量评分                               │
│                  每帧 quality_score 0-100                      │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  扫描入库/登记    │
                    │  stage: raw_pool │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        真实数据标注    质检审核通过    仿真数据生成
              │              │              │
              └──────────────┼──────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  build 入库      │
                    │  自动版本快照     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  模型训练/评估    │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │ 评估反馈 → 数据缺口│
                    │ mAP低 → 仿真补数据 │
                    └─────────────────┘
```

### 二、视频预处理管线设计

#### 2.1 数据模型
```
预处理Job:
  id, source_path, status, created_at
  params: {denoise_method, dedup_threshold, anomaly_filters, keyframe_interval}
  result: {
    input_frames, output_frames, removed_duplicates,
    removed_anomalies, quality_distribution, processing_time
  }
```

#### 2.2 去噪 (Denoise)
| 方法 | 适用场景 | 计算量 |
|------|---------|--------|
| `fast_nonlocal_means` | 夜间/低光图像 | 中 |
| `bilateral_filter` | 保留边缘的平滑 | 低 |
| `temporal_median` | 连续帧时序去噪 | 高 |
| `none` | 光线充足的日间 | 无 |

#### 2.3 去重 (Dedup)
| 方法 | 阈值 | 说明 |
|------|------|------|
| `ssim` | 0.95 | 结构相似度 > 0.95 视为重复 |
| `phash` | hamming ≤ 5 | 感知哈希距离 ≤ 5 视为重复 |
| `histogram` | correlation > 0.98 | 直方图相关 > 0.98 视为重复 |

#### 2.4 异常过滤 (Anomaly)
| 检测项 | 阈值 | 动作 |
|--------|------|------|
| 全黑图 | mean_pixel < 5 | 丢弃 |
| 全白图 | mean_pixel > 250 | 丢弃 |
| 模糊图 | Laplacian variance < 100 | 丢弃 |
| 过曝 | overexposed_ratio > 0.4 | 丢弃 |
| 遮挡 | black_border_ratio > 0.3 | 标记 |

#### 2.5 关键帧提取策略
| 策略 | 适用场景 |
|------|---------|
| `fixed_interval` | 等间隔采样，每 N 帧取 1 帧 |
| `scene_change` | 检测场景切换时抽取 |
| `motion_peak` | 运动幅度最大帧（最有信息量） |
| `quality_top` | 取质量分最高的 K% |

### 三、API 设计

```
# 视频预处理
POST   /api/v1/preprocess/analyze        # 分析视频（不解码全量，采样统计）
POST   /api/v1/preprocess/run            # 执行预处理（异步 Job）
GET    /api/v1/preprocess/jobs           # 预处理任务列表
GET    /api/v1/preprocess/jobs/{id}      # 任务详情 + 统计
GET    /api/v1/preprocess/jobs/{id}/frames  # 预览帧（抽样展示）
POST   /api/v1/preprocess/jobs/{id}/ingest # 处理后数据入库

# 仿真生成
POST   /api/v1/simulate/generate         # 提交生成任务
GET    /api/v1/simulate/jobs             # 生成历史
GET    /api/v1/simulate/jobs/{id}/images # 预览生成结果
POST   /api/v1/simulate/jobs/{id}/ingest # 入库
```

### 四、前端页面设计

#### 4.1 视频预处理页 `/labeling/preprocess`
```
┌─ 配置面板 ────────────────────────────┐
│ 源路径: [________________] [浏览]      │
│                                       │
│ 去噪: [none ▼]                        │
│ 去重: [ssim ▼]  阈值: [0.95]          │
│ 异常: ☑全黑 ☑模糊 ☑过曝              │
│ 关键帧: [fixed_interval ▼] 间隔: [10] │
│                                       │
│ [🔍 分析视频]  [▶ 执行预处理]          │
├─ 分析结果 ────────────────────────────┤
│ 总帧数: 12,340                        │
│ 预计去重后: ~8,500 (去重率 31%)        │
│ 异常帧: 234 (1.9%)                     │
│ 质量分布: ████████░░ 85% good          │
├─ 处理后预览 ──────────────────────────┤
│ [缩略图网格] [采样帧对比] [去重前后对比] │
└──────────────────────────────────────┘
```

#### 4.2 仿真工坊页 `/labeling/simulate` (已实现，见源码)

### 五、后端模块结构

```
platform/as_platform/data/
├── simulate.py       # 世界模型仿真 API 层 (已实现)
├── preprocess.py     # 视频预处理管线 (待实现)
│   ├── denoise.py    # 去噪算法
│   ├── dedup.py      # 去重算法
│   └── anomaly.py    # 异常检测
└── quality.py        # 图像质量评分引擎
```

### 六、依赖

```txt
# 视频预处理
opencv-python-headless>=4.8.0   # 帧提取、去噪、Laplacian
scikit-image>=0.21.0            # SSIM、直方图
Pillow>=10.0.0                  # (已有) 基础图像操作
imagehash>=4.3.1                # 感知哈希去重
```
| 🆕 P2 | 标注质量抽检 | ❌ |

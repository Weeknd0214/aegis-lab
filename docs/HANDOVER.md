# HSAP 项目交接文档

> **HSAP** — Huaxu Sentinel Active Safety Platform / 华胥 Sentinel 主动安全平台
>
> 最后更新：2026-06-12 | 交接人：chengfanglu

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈](#2-技术栈)
3. [项目架构](#3-项目架构)
4. [环境与部署](#4-环境与部署)
5. [核心功能模块](#5-核心功能模块)
6. [API 概览](#6-api-概览)
7. [数据库设计](#7-数据库设计)
8. [配置与环境变量](#8-配置与环境变量)
9. [日常运维](#9-日常运维)
10. [当前完成状态与待办](#10-当前完成状态与待办)
11. [关键文件索引](#11-关键文件索引)
12. [常见问题排查](#12-常见问题排查)

---

## 1. 项目概述

### 1.1 定位

HSAP 是一个**卡车主动安全算法的迭代平台**，覆盖三大感知任务：

| 任务 | 算法 | 说明 |
|------|------|------|
| DMS (Driver Monitoring) | YOLOv6 | 驾驶员状态监测（疲劳、分心、打电话等） |
| Lane Detection | UFLD | 车道线检测 |
| ADAS Perception | — | 辅助驾驶感知（规划中） |

**HSAP 不是训练框架**，它是一个**协作编排平台**，覆盖从数据到模型的全生命周期：

```
数据采集 → 数据上载 → 扫描入库 → 送标(CVAT) → 标注审核 → 构建数据集 → 模型训练 → 评估 → 晋级上线
```

### 1.2 核心能力

- 🌐 **Web UI + API**：React 前端 + FastAPI 后端，四个功能模块
- 🏷️ **标注管理**：集成 CVAT 标注引擎，支持供应商回传
- 🔍 **审核治理**：所有写操作经过审核队列，RBAC 权限控制
- 🚛 **车队地图**：GPS/T-Box 轨迹追踪，模拟数据生成
- 🤖 **算法适配**：DMS YOLO 和 Lane UFLD 适配器，支持本地/平台双轨训练
- 📋 **飞书集成**：SSO 登录、Bitable 数据同步、消息通知

### 1.3 代码仓库

```
路径：/home/chengfanglu/DATA/HSAP
远端：git@github.com:Reuonny/HSAP.git （待确认）
分支：main
关键提交：
  - e72bc06 feat: HSAP platform v2 — modular navigation, quality review, audit log, world model simulation
  - 7c43b44 feat: initial HSAP platform
```

---

## 2. 技术栈

### 2.1 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 主要开发语言 |
| FastAPI | latest | Web 框架 |
| Uvicorn | latest | ASGI 服务器 |
| SQLAlchemy | 2.0 | ORM |
| PostgreSQL | 16 | 生产数据库 |
| SQLite | — | 本地开发备选（自动回退） |
| Redis | 7 | 任务队列 + 发布订阅 |
| python-jose | latest | JWT 令牌 |
| httpx | latest | HTTP 客户端 |

### 2.2 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | latest | 类型安全 |
| Vite | 5 | 构建工具 |
| Tailwind CSS | 3 | 样式框架 |
| React Router | v5 | 路由管理 |

### 2.3 基础设施

| 技术 | 版本 | 用途 |
|------|------|------|
| Docker Compose | v2 | 服务编排 |
| CVAT | latest | 标注引擎 |
| MinIO | latest | S3 兼容存储（可选） |

---

## 3. 项目架构

### 3.1 三层解耦设计

```
HSAP/
├── platform/              ← 编排层：API、鉴权、审核、任务队列、Web 前端
│   ├── as_platform/       # FastAPI 后端 Python 包
│   └── web/               # React + Vite + TypeScript 前端
├── algorithms/            ← 算法层：DMS YOLO / Lane UFLD 适配器
├── datasets/              ← 数据层：数据集包、标注配置、数据注册表
├── scripts/               ← 运维脚本（初始化、冒烟测试、同步、worker）
├── docs/                  ← 文档（20+ 篇）
├── lake/                  ← 数据湖暂存区
├── reports/               ← 报告、CSV、图表
├── manifests/             ← 运行时配置（feishu.env、DB、日志）
├── as.py                  ← CLI 入口
├── workflow.registry.yaml ← 中央注册表
├── docker-compose.yml     ← Docker 服务编排
├── docker-compose.cvat.yml← CVAT 标注引擎编排
├── Dockerfile             ← Python 3.11-slim 镜像
└── Makefile               ← 快捷命令
```

### 3.2 服务拓扑（Docker Compose）

```
                    ┌──────────────────┐
                    │   hsap-platform  │  ← FastAPI :8787 + 静态前端
                    │   (uvicorn)      │
                    └───────┬──────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
     ┌────────▼──────┐ ┌───▼────┐ ┌──────▼──────────┐
     │ hsap-postgres │ │ hsap-  │ │  hsap-worker    │
     │ PostgreSQL 16 │ │ redis  │ │  (异步任务消费者) │
     │ :5433(host)   │ │ :6380  │ │                  │
     └───────────────┘ └────────┘ └─────────────────┘

     可选服务 (profile: minio):
     ┌──────────┐  ┌──────────────┐
     │  minio   │  │  minio-init  │
     │ :9000    │  │  (初始化桶)   │
     └──────────┘  └──────────────┘

     可选服务 (docker-compose.cvat.yml):
     ┌──────────────────────────────────────────┐
     │ CVAT 标注引擎 (完整服务栈)                 │
     │ cvat_server + cvat_ui + workers + ...    │
     │ 代理端口 :8080                            │
     └──────────────────────────────────────────┘
```

### 3.3 后端包结构 (`platform/as_platform/`)

```
as_platform/
├── api/           # FastAPI 路由 (auth, labeling, fleet, models, system, delivery, feishu)
├── auth/          # 飞书 OAuth、JWT 令牌、用户管理、RBAC 依赖
├── db/            # SQLAlchemy 引擎、数据模型（13+ 表）、初始化/迁移
├── data/          # 数据湖核心：采集管线、批次暂存、目录缓存
│   └── ingest/    # 采集适配器 (dms_coco, dms_yolo, dms_inbox_raw, lane_lines, lane_mask)
├── labeling/      # 标注服务：CVAT 客户端、批次暂存、供应商导入、进度追踪
├── audit/         # 审核队列和预览逻辑
├── jobs/          # 任务队列（Redis List / 内存）、执行器、飞书 Bitable 同步
├── deliveries/    # 交付/模型交接服务
├── fleet/         # 车队地图：GPS 追踪、T-Box 采集、模拟数据
├── training/      # 训练编排服务
├── agents/        # Agent 工作流图 (ingest_flow, labeling_flow, train_promote_flow)
├── integrations/  # 第三方集成：飞书 Bitable、飞书通知
├── redis/         # Redis 发布订阅总线
├── config.py      # 中央配置（AS_* 环境变量）
└── sdk.py         # Python SDK
```

### 3.4 前端模块结构 (`platform/web/src/`)

前端采用 **4 模块 + 侧边栏导航** 架构：

| 模块 | 路由前缀 | API 前缀 | 子页面 |
|------|---------|---------|--------|
| 🏷️ **数据送标** | `/labeling/*` | `/api/v1/labeling/*` | 数据上载、送标工作台、标注进度、导出与入库、批次台账、数据目录 |
| 🤖 **模型管理** | `/models/*` | `/api/v1/models/*` | 模型概览、训练提交、训练记录、评估管理、模型晋级 |
| 🚛 **车队管理** | `/fleet/*` | `/api/v1/fleet/*` | 车队总览、车辆管理、实时地图、行程记录、T-Box配置 |
| ⚙️ **系统管理** | `/system/*` | `/api/v1/system/*` | 审核队列、任务监控、执行日志、用户管理 |

**旧路由兼容重定向**（`/deliveries` → `/labeling/deliveries` 等）

---

## 4. 环境与部署

### 4.1 快速启动（Docker，推荐）

```bash
# 1. 首次克隆后初始化
bash scripts/init_after_clone.sh    # 生成 .env 和 manifests/feishu.env

# 2. 启动全部服务
bash scripts/dev_up.sh              # 或 make up

# 3. 启动平台 + CVAT 标注引擎
docker compose -f docker-compose.yml -f docker-compose.cvat.yml up -d

# 4. 验证
curl http://127.0.0.1:8787/api/v1/health
# 或 make health
```

### 4.2 本地开发（仅平台，基础设施用 Docker）

```bash
# 1. 启动基础设施
docker compose up -d postgres redis

# 2. 本地启动平台
pip install -r requirements.txt
bash scripts/run_local.sh

# 3. 或前端热重载开发
make dev    # Vite :5173
```

### 4.3 Docker 服务端口映射

| 服务 | 容器内端口 | 宿主机端口 | 说明 |
|------|----------|-----------|------|
| platform | 8787 | 8787 | FastAPI + Web UI |
| postgres | 5432 | 5433 | PostgreSQL 16 |
| redis | 6379 | 6380 | Redis 7 |
| minio (可选) | 9000/9001 | 9000/9001 | S3 存储 |
| cvat (可选) | — | 8080 | CVAT 标注引擎 |

### 4.4 停止服务

```bash
make down    # 停止全部（含 CVAT 和 dev profile）
```

---

## 5. 核心功能模块

### 5.1 数据送标（Labeling）

完整的数据送标工作流：

```
数据上载 → 送标工作台（扫描入库） → 创建标注任务(CVAT) → 标注进度追踪 → 导出与入库 → 批次台账
```

**关键文件：**
- `platform/as_platform/labeling/` — 标注服务后端
- `platform/as_platform/data/ingest/` — 数据采集适配器
- `platform/web/src/modules/labeling/` — 前端页面
- `docs/LABELING_SOP.md` — 标准操作流程
- `docs/LANE_LABELING_PLAN.md` — 车道线标注方案
- `docs/LABEL_STUDIO_UI_MIGRATION.md` — UI 迁移记录

### 5.2 模型管理（Models）

模型全生命周期管理：

```
数据集版本快照 → 训练提交 → 训练记录追踪 → 评估管理(mAP对比) → 模型晋级
```

**关键文件：**
- `platform/as_platform/api/models_routes.py` — 模型 API
- `platform/as_platform/training/` — 训练编排
- `platform/web/src/modules/models/` — 前端页面

### 5.3 车队管理（Fleet）

车队 GPS 追踪与数据采集管理：

- 车辆注册与管理
- 实时地图展示（高德/OSM）
- T-Box 设备数据采集
- 行程记录与里程碑
- 模拟 GPS 数据生成（开发用）

**关键文件：**
- `platform/as_platform/fleet/` — 车队服务后端
- `platform/web/src/modules/fleet/` — 前端页面
- `docs/FLEET_MAP.md` — 车队地图文档

### 5.4 系统管理（System）

平台治理：

- **审核队列**：所有写操作（构建/训练/晋级/注册）需要审核，支持批量操作
- **任务监控**：异步任务状态追踪，自动刷新
- **执行日志**：Agent 工作流 Trace 查看
- **用户管理**：飞书用户信息、角色分配、分页

### 5.5 飞书集成

| 功能 | 状态 | 说明 |
|------|------|------|
| SSO 登录 | ✅ 已实现 | OAuth2 认证，JWT 令牌 |
| Bitable 同步 | ✅ 已实现 | HSAP 数据 ↔ 飞书多维表格 |
| 审核通知 | ❌ 待实现 | 审核提交/结果通知到飞书群 |
| 角色同步 | ✅ 已实现 | 按飞书部门自动分配角色 |

**关键文件：**
- `platform/as_platform/auth/` — 飞书 OAuth + JWT
- `platform/as_platform/integrations/feishu_bitable.py` — Bitable 集成
- `platform/as_platform/integrations/feishu_notify.py` — 通知（待接入）
- `docs/FEISHU_BITABLE_OPS.md` — Bitable 运维文档
- `docs/FEISHU_DEV_HANDOFF.md` — 飞书开发交接

### 5.6 CLI 工具 (`as.py`)

```bash
python as.py status                     # 查看工作区和活动数据包
python as.py pending                    # 查看待审核项
python as.py add dms dam --src ...      # 注册 DMS 批次
python as.py build dms dam              # 从活动数据包构建数据集
python as.py train dms dam --track local     # 本地训练
python as.py train dms dam --track platform  # 平台训练（需审核）
```

### 5.7 世界模型仿真（新功能）

用于生成合成训练数据的仿真 API，已实现基础框架：

**API 端点：**
- `POST /api/v1/simulate/generate` — 提交生成任务
- `GET /api/v1/simulate/jobs` — 查看生成历史
- `GET /api/v1/simulate/jobs/{id}/images` — 预览生成结果
- `POST /api/v1/simulate/jobs/{id}/ingest` — 入库

**视频预处理管线**：设计了但尚未完全实现。包括去噪（非局部均值/双边滤波）、去重（SSIM/感知哈希）、异常过滤（全黑/模糊/过曝检测）、关键帧提取。

---

## 6. API 概览

### 6.1 主要路由

| 路由前缀 | 文件 | 关键端点 |
|---------|------|---------|
| `/api/v1/auth` | `auth_routes.py` | 飞书登录/回调、用户管理、角色分配 |
| `/api/v1/labeling` | `labeling_routes.py` | 标注活动管理、扫描入库、进度、供应商导入 |
| `/api/v1/models` | `models_routes.py` | 模型生命周期、训练、评估、晋级 |
| `/api/v1/fleet` | `fleet_routes.py` | 车辆、轨迹、行程、T-Box |
| `/api/v1/system` | `system_routes.py` | 审核队列、任务监控、执行日志 |
| `/api/v1/delivery` | `delivery_routes.py` | 批次交付、Bitable 集成 |
| `/api/v1/feishu` | `feishu_routes.py` | Bitable Webhook 回调 |
| `/api/v1/` (根) | `server.py` | health, dashboard, catalog, approvals, simulate, agents |

### 6.2 核心端点速查

```bash
# 健康检查
GET  /api/v1/health

# 首页仪表盘数据
GET  /api/v1/dashboard

# 数据目录
GET  /api/v1/catalog
POST /api/v1/catalog

# 审核流程
GET  /api/v1/approvals
POST /api/v1/approvals/{id}/approve
POST /api/v1/approvals/{id}/reject
GET  /api/v1/approvals/{id}/preview

# 任务队列
GET  /api/v1/jobs
POST /api/v1/jobs

# 文件上传
POST /api/v1/data/upload/file

# Agent 工作流
POST /api/v1/agents/invoke

# Swagger 文档
GET  /docs    # FastAPI 自动生成的交互式 API 文档
```

---

## 7. 数据库设计

### 7.1 核心表（13+ 张）

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `users` | 用户账户 | feishu_open_id, name, email, department |
| `roles` | RBAC 角色 | admin, reviewer, engineer, labeler, viewer |
| `permissions` | 细粒度权限 | read:catalog, write:approval_review 等 13 个 |
| `user_roles` | 用户-角色 M2M | — |
| `role_permissions` | 角色-权限 M2M | — |
| `approvals` | 审核队列 | action, params, status, reviewed_by |
| `jobs` | 任务队列 | action, status, approval_id, params, result |
| `dataset_candidates` | 数据集候选 | project, task, mode, status, format |
| `batch_deliveries` | 批次交付 | project, task, batch_name, status |
| `feishu_bitable_links` | 飞书 Bitable 映射 | hsap_record_id, bitable_record_id |
| `fleet_vehicles` | 车队车辆 | plate_no, tbox_device_id, GPS 坐标 |
| `fleet_collection_runs` | 采集行程 | vehicle_id, run_no, mileage |
| `fleet_track_points` | GPS 轨迹点 | lat, lng, speed, heading |
| `fleet_run_milestones` | 行程里程碑 | 途经点/事件标记 |
| `labeling_campaigns` | 标注活动 | project, task, batch, status, CVAT 引用 |
| `labeling_task_assignments` | 标注任务分配 | 每张图片的标注员分配 |
| `labeling_export_jobs` | 导出/预测任务 | 导出参数、结果路径 |

### 7.2 数据库模式

- **生产**：PostgreSQL 16，通过 Docker Compose 启动
- **本地开发**：自动回退到 SQLite (`manifests/platform.db`)
- **迁移**：`scripts/db_migrate_from_sqlite.py` 支持 SQLite → PostgreSQL 迁移

### 7.3 权限体系

**5 个默认角色** + **13 个细粒度权限**：

```
admin    → 全部权限
reviewer → read:catalog + write:approval_review
engineer → read:catalog + write:dataset + write:training + write:model
labeler  → read:catalog + write:labeling
viewer   → read:catalog
```

飞书部门 ID 自动映射到角色（在 `db/init_db.py` 中配置）。

---

## 8. 配置与环境变量

### 8.1 核心环境变量（`AS_*` 前缀）

#### 数据库
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AS_DB_HOST` | `127.0.0.1` | PostgreSQL 主机 |
| `AS_DB_PORT` | `5432` | PostgreSQL 端口 |
| `AS_DB_USER` | `as_platform` | 数据库用户 |
| `AS_DB_PASSWORD` | `as_platform` | 数据库密码 |
| `AS_DB_NAME` | `as_platform` | 数据库名 |
| `AS_DATABASE_URL` | (自动构建) | 完整连接 URL |

#### Redis / 任务队列
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AS_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis 连接 |
| `AS_JOB_EXECUTOR` | `thread` | 任务执行模式：`thread` 或 `worker` |
| `AS_JOB_QUEUE_KEY` | `as:job_queue` | Redis 队列键名 |

#### 认证
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AS_JWT_SECRET` | (必须修改) | JWT 签名密钥 |
| `AS_JWT_EXPIRE_HOURS` | `168` | 令牌有效期 |
| `AS_DEV_AUTH` | `false` | 绕过飞书登录 |
| `AS_FORCE_DEV_AUTH` | `false` | 强制开发认证 |
| `FEISHU_APP_ID` | (空) | 飞书应用 ID |
| `FEISHU_APP_SECRET` | (空) | 飞书应用密钥 |

#### 飞书 Bitable
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FEISHU_BITABLE_APP_TOKEN` | (空) | Bitable App Token |
| `FEISHU_BITABLE_TABLE_ID` | (空) | Bitable 表 ID |
| `FEISHU_BITABLE_SYNC_ENABLED` | `false` | 启用定期同步 |
| `FEISHU_BITABLE_SYNC_INTERVAL_SEC` | `120` | 同步间隔 |

#### 工作区 / 数据路径
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AS_WORKSPACE_ROOT` | (自动检测) | 外部数据工作区路径 |
| `AS_DATA_LAKE_ROOT` | (自动检测) | 数据湖根路径 |

#### 车队
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AS_FLEET_MAP_ENABLED` | `1` | 启用车队地图 API |
| `AS_FLEET_MOCK_SEED` | `1` | 种子演示车辆 |
| `AS_FLEET_MOCK_SIMULATE` | `1` | 自动模拟 GPS |
| `AS_FLEET_SIM_INTERVAL_SEC` | `8` | 模拟间隔 |

### 8.2 敏感配置文件（Git 忽略）

- **`.env`** — Docker Compose 环境变量
- **`manifests/feishu.env`** — 飞书凭证（`FEISHU_APP_ID`, `FEISHU_APP_SECRET` 等）

---

## 9. 日常运维

### 9.1 常用命令速查

```bash
# === 服务管理 ===
make up          # 启动全部服务
make down        # 停止全部服务
make ps          # 查看容器状态
make logs        # 查看 platform + worker 日志
make health      # 检查 API 健康状态
make build       # 重新构建镜像

# === 开发调试 ===
make dev         # 启动前端热重载开发 (:5173)

# === 查看日志 ===
docker compose logs -f platform    # 后端日志
docker compose logs -f worker      # Worker 日志
docker compose logs -f postgres    # 数据库日志

# === 数据库操作 ===
docker compose exec postgres psql -U as_platform -d as_platform  # 进入 PostgreSQL

# === API 测试 ===
curl http://127.0.0.1:8787/api/v1/health
curl http://127.0.0.1:8787/docs    # Swagger 交互文档

# === CLI ===
python as.py status      # 查看工作区状态
python as.py pending     # 查看待审核项
```

### 9.2 数据备份

```bash
# PostgreSQL 备份
docker compose exec postgres pg_dump -U as_platform as_platform > backup_$(date +%Y%m%d).sql

# PostgreSQL 恢复
docker compose exec -T postgres psql -U as_platform as_platform < backup_20260612.sql
```

### 9.3 冒烟测试

```bash
bash scripts/smoke_api.sh           # API 基础功能测试
bash scripts/smoke_labeling.sh      # 标注流程测试
bash scripts/smoke_manifest_alignment.sh  # 配置一致性检查
```

### 9.4 环境重置

```bash
# 完全重置（清除所有数据）
docker compose down -v    # -v 删除 volumes（数据库+Redis 数据）

# 仅重置标注状态
bash scripts/reset_labeling.sh
```

---

## 10. 当前完成状态与待办

### 10.1 已完成功能 ✅

| 模块 | 页面 | 状态 |
|------|------|:--:|
| 数据送标 | 送标工作台（扫描入库） | ✅ |
| 数据送标 | 标注进度（Campaigns） | ✅ |
| 数据送标 | 导出与入库（供应商回传） | ✅ |
| 数据送标 | 批次台账（Deliveries） | ✅ |
| 数据送标 | 数据目录（可视化） | ✅ |
| 模型管理 | 模型概览（KPI 卡片） | ✅ |
| 模型管理 | 数据集版本（自动快照+diff） | ✅ |
| 模型管理 | 训练提交（表单校验） | ✅ |
| 模型管理 | 训练记录（分页+展开详情） | ✅ |
| 模型管理 | 评估管理（mAP 对比图） | ✅ |
| 模型管理 | 模型晋级（版本选择+历史） | ✅ |
| 车队管理 | 总览 / 车辆 / 地图 / 行程 / T-Box | ✅ |
| 系统管理 | 审核队列（批量操作+驳回分类） | ✅ |
| 系统管理 | 任务监控（自动刷新） | ✅ |
| 系统管理 | 执行日志（Trace 查看） | ✅ |
| 系统管理 | 用户管理（飞书信息+分页） | ✅ |
| 世界模型 | 仿真工坊（生成合成数据） | ✅ |

### 10.2 待开发功能 ❌

| 优先级 | 功能 | 预估工时 | 说明 |
|:--:|------|:--:|------|
| **P0** | 首页仪表盘 | 1天 | KPI 卡片、审核待办、车队实时卡片、最近活动时间线 |
| **P0** | 飞书审核通知 | 0.5天 | 审核提交/通过/驳回时飞书群通知，复用已有 `integrations/feishu_notify.py` |
| **P1** | 入库基础质检 | 1天 | 图片可读性、分辨率分布、标注格式校验、越界检测 |
| **P1** | 操作审计日志 | 0.5天 | 新增 `OperationLog` 表，埋点关键操作，前端时间线页面 |
| **P2** | 标注质量抽检 | 1.5天 | 随机抽取标注结果审核，统计标注员准确率 |
| **P2** | 模型预标 | 2天 | 已有模型推理 → 预标注 → 标注员修正 |
| **P3** | 模型部署追踪 | — | 实验→候选→生产→退役 状态追踪 |
| **P3** | 采集任务管理 | — | 创建采集任务、指派车辆、回传追踪 |
| **—** | 视频预处理管线 | — | 去噪/去重/异常过滤/关键帧提取，代码框架已设计 |

> 详细开发计划见 `docs/DEVELOPMENT_ROADMAP.md` 和 `CLAUDE.md` 末尾。

---

## 11. 关键文件索引

### 11.1 核心代码

| 文件/目录 | 说明 |
|----------|------|
| `platform/as_platform/api/server.py` | FastAPI 主入口，挂载所有路由 |
| `platform/as_platform/config.py` | 中央配置（读环境变量） |
| `platform/as_platform/sdk.py` | Python SDK |
| `platform/as_platform/db/models.py` | 全部数据模型定义 |
| `platform/as_platform/db/init_db.py` | 数据库初始化 + 种子数据 |
| `as.py` | CLI 入口 |
| `workflow.registry.yaml` | 中央注册表（项目/数据包/规则） |
| `algorithms/registry.yaml` | 算法注册表 |
| `scripts/worker.py` | 异步任务 Worker |

### 11.2 配置文件

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | Docker 服务编排 |
| `docker-compose.cvat.yml` | CVAT 标注引擎编排 |
| `Dockerfile` | 镜像构建 |
| `Makefile` | 运维快捷命令 |
| `.env` | Docker Compose 环境变量（Git 忽略） |
| `manifests/feishu.env` | 飞书凭证（Git 忽略） |
| `requirements.txt` | Python 依赖 |

### 11.3 文档

| 文档 | 说明 |
|------|------|
| `CLAUDE.md` | AI 助手指南（项目最详细的文档） |
| `docs/DEVELOPMENT_GUIDE.md` | 架构、约定、设计决策 |
| `docs/DEVELOPMENT_ROADMAP.md` | Q2 2026 开发路线图 |
| `docs/DATA_LAKE_CHECKLIST.md` | 数据湖操作清单 |
| `docs/LABELING_SOP.md` | 标注标准操作流程 |
| `docs/FLEET_MAP.md` | 车队地图文档 |
| `docs/FEISHU_BITABLE_OPS.md` | 飞书 Bitable 运维 |
| `docs/BATCH_DELIVERY_OPS.md` | 批次交付操作 |
| `docs/MINIO_STAGING.md` | MinIO S3 暂存配置 |
| `docs/PILOT_BATCH.md` | 试点批次流程 |
| `docs/LANE_LABELING_PLAN.md` | 车道线标注方案 |
| `docs/GIT_PUSH.md` | Git 推送清单 |
| `docs/HANDOVER.md` | 👈 **本文档** |

---

## 12. 常见问题排查

### 12.1 服务启动失败

```bash
# 检查容器状态
docker compose ps

# 查看具体服务日志
docker compose logs platform
docker compose logs postgres
docker compose logs redis

# 常见原因：
# 1. 端口冲突 → 修改 .env 中的端口映射
# 2. PostgreSQL 未就绪 → 等待 healthcheck 通过
# 3. 飞书凭证缺失 → 检查 manifests/feishu.env
```

### 12.2 数据库连接问题

```bash
# 测试 PostgreSQL 连接
docker compose exec postgres pg_isready -U as_platform -d as_platform

# 进入数据库查看
docker compose exec postgres psql -U as_platform -d as_platform

# 本地开发时 SQLite 自动回退，检查：
ls -la manifests/platform.db
```

### 12.3 飞书登录问题

```bash
# 确认飞书凭证已配置
cat manifests/feishu.env

# 开发模式绕过飞书登录
export AS_DEV_AUTH=true
export AS_FORCE_DEV_AUTH=true

# 检查回调 URI 配置
# 飞书应用控制台 → 安全设置 → 重定向 URL
```

### 12.4 标注/CVAT 问题

```bash
# 确认 CVAT 服务状态
docker compose -f docker-compose.yml -f docker-compose.cvat.yml ps

# CVAT 公开地址
echo $CVAT_PUBLIC_URL    # 默认 http://127.0.0.1:8080

# 检查 CVAT 日志
docker compose -f docker-compose.yml -f docker-compose.cvat.yml logs cvat_server
```

### 12.5 任务队列积压

```bash
# 检查 Worker 是否在运行
docker compose ps worker

# 查看 Worker 日志
docker compose logs worker

# 检查 Redis 队列长度
docker compose exec redis redis-cli LLEN as:job_queue

# 模式确认：线程模式不需要 worker，Redis 模式需要 worker
# AS_JOB_EXECUTOR=worker → 必须有 worker 容器
# AS_JOB_EXECUTOR=thread → 不需要 worker（开发环境）
```

### 12.6 前端构建/热重载

```bash
# 前端代码在 platform/web/
cd platform/web/

# 安装依赖
npm install

# 开发模式（热重载）
npm run dev      # Vite :5173

# 生产构建
bash scripts/build_web.sh
```

---

## 附录

### A. Git 忽略规则（不要提交这些）

- `.env`、`manifests/feishu.env`（凭证）
- `*.pt`、`*.pth`、`*.onnx`、`*.rknn`（模型权重）
- 图片/视频数据集文件
- `node_modules/`
- `__pycache__/`、`*.pyc`
- `manifests/platform.db`（SQLite 数据库）
- `reports/`（报告输出）

### B. Python 路径约定

- 所有代码从仓库根目录运行，`PYTHONPATH=platform`
- Python 包名为 `as_platform`（历史命名保留）

### C. 外部依赖

- 飞书应用（SSO + Bitable）
- CVAT 标注引擎（可选，通过 Docker Compose 集成）
- 训练服务器（通过 `scripts/sync_to_server.sh` 同步）
- 外部工作区（大文件存储，Docker 中挂载到 `/data/workspace`）

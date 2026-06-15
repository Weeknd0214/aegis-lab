# HSAP — Huaxu Sentinel Active Safety Platform

**华胥 Sentinel 主动安全算法迭代平台**（HSAP）：卡车主动安全（DMS / Lane / ADAS）算法迭代平台，含 **Web UI + API + 审核 + Job 队列 + CVAT 标注 + 算法适配器**。

克隆本仓库即可运行平台；**算法源码与数据集脚手架已内嵌**，无需依赖本地软链。大文件（图像、训练权重）通过外部 `workspace` 或 **送标数据湖** 挂载，不进入 Git。

---

## 仓库结构

```text
HSAP/
├── as.py / workflow.registry.yaml
├── platform/
│   ├── as_platform/           # FastAPI 后端
│   │   └── labeling/          # CVAT 客户端、格式转换、任务分配
│   └── web/                   # React (Vite) 前端
├── algorithms/
│   ├── dms_yolo/code/         # DMS YOLO 训练代码
│   └── lane_ufld/code/        # Lane UFLD 代码
├── datasets/
│   ├── dms/                   # DMS 配置/脚本
│   ├── lane/                  # Lane 列表与脚本
│   ├── adas -> ../../data/送标/adas   # ADAS 送标数据湖（符号链接）
│   └── labeling.registry.yaml # 标注 profile（cuboid_7cls 等）
├── vendor/cvat/patches/       # CVAT no_auth + iframe 补丁
├── scripts/                   # dev_up、build_web、reset_labeling 等
├── docs/HANDOVER.md           # 详细交接文档
├── docker-compose.yml
├── docker-compose.cvat.yml    # 内置 CVAT 全套服务
└── manifests/
```

| 内容 | 是否在 Git 中 | 说明 |
|------|---------------|------|
| 平台 + 前端 + 适配器 | ✅ | 直接提交 |
| CVAT 补丁 / compose | ✅ | `vendor/cvat/patches/` |
| 算法 Python 源码 | ✅ | `scripts/vendor_workspace.sh` 同步 |
| 数据集 yaml/脚本 | ✅ | 不含图像 |
| 送标图像 / 标定 / 标注 | ❌ | 数据湖 `DATA/data/送标/`，volume 挂载 |
| 图像 / 视频 / 权重 | ❌ | `.gitignore` 排除；用 workspace 挂载 |

---

## 快速开始（Docker，推荐）

**依赖：** Docker 20+、Docker Compose v2

```bash
git clone https://git.sanyele.com/ChengFang.LU/HSAP.git
cd HSAP

bash scripts/init_after_clone.sh   # 生成 .env / feishu.env
bash scripts/dev_up.sh             # 或: make up
```

`make up` 会同时启动 **HSAP 平台** 与 **内置 CVAT**（无需单独部署 BK2/cvat，无需 CVAT 账号登录）。

| 服务 | 地址 | 说明 |
|------|------|------|
| HSAP 平台 UI + API | http://127.0.0.1:8787 | 登录、送标、标注、审核 |
| CVAT 标注画布 | http://127.0.0.1:8080 | 由 HSAP iframe 嵌入；内部引擎 no_auth |
| PostgreSQL | localhost:5433 | 默认映射端口（见 `.env`） |
| Redis | localhost:6380 | Job 队列 |

```bash
make logs      # platform / worker 日志
make down      # 停止平台 + CVAT
make dev       # 额外启动 Vite 热更新 :5173
```

**开发登录：** 默认 `manifests/feishu.env` 中 `AS_DEV_AUTH=true`，无需飞书即可登录。

**改 HSAP 前端后（源码在 `platform/web/`）：** 须执行 `bash scripts/build_web.sh` 并 `docker compose restart platform`，否则 8787 仍为旧静态包。

---

## 标注与送标

HSAP 统一使用 **CVAT** 作为标注画布；账号、任务分配、权限均在 HSAP 管理，CVAT 仅作内部引擎。

### 流程概览

```text
数据湖登记批次 → 协调员「开标」→ CVAT 自动建 Task / 上传图片
    → 协调员分配任务（飞书通讯录选人 + 可选 DM 通知）
    → 标注员「我的标注」进入 → CVAT 画框/ Cuboid → 保存 → 同步回数据湖
    → 协调员提交批次 → 质检 → 导出入库
```

### 角色与页面

| 角色 | 典型页面 |
|------|----------|
| 协调员 (engineer) | 送标工作台、标注进度、任务分配 |
| 标注员 (labeler) | **我的标注**（默认落地页）、标注页 |
| 审核员 (reviewer) | 审核队列 |

### 支持的标注类型

| Profile | 范围 | CVAT 工具 |
|---------|------|-----------|
| `ddaw` / `addw` 等 | DMS 2D 检测 | Rectangle |
| `lane__lane_v1` | 车道线 | Polyline |
| `cuboid_7cls` | ADAS 单目 3D Cuboid（7 类） | Cuboid |

ADAS 7 类：`car`, `pedestrian`, `truck`, `bus`, `motorcycle`, `tricycle`, `traffic cone`

### 送标数据湖（ADAS Cuboid 示例）

宿主机目录（与仓库平级）：

```text
DATA/data/送标/adas/inbox/cuboid_7cls/<batch>/
├── batch.meta.yaml
├── images/
├── calib/              # 相机内参（可选）
│   └── cam0_front_6mm.yaml
└── labels/
    └── quaternion_json/  # 3D 预标注 JSON（可选）
```

`.env` / `docker-compose.yml` 默认将 `../data` 挂载为容器内 `/data/data`。登记与开标：

```bash
# API 或平台 UI：register-batch → 标注进度 → 开标
# 批次出现在「标注进度」后即可分配、标注
```

清空送标/标注 DB 记录（保留账号）：`bash scripts/reset_labeling.sh`

---

## 数据挂载

### 外部 workspace（DMS / Lane 大文件）

```bash
# .env 中设置
AS_WORKSPACE_ROOT=/path/to/DATA/workspace

bash scripts/setup_links.sh
docker compose -f docker-compose.yml -f docker-compose.cvat.yml up -d --build
```

### 送标数据湖（ADAS 等）

```bash
# .env 可选覆盖宿主机路径（默认 ../data）
AS_DATA_LAKE_HOST=/path/to/DATA/data
```

确保 `HSAP/datasets/adas` 符号链接指向 `data/送标/adas`（clone 后若缺失可手动 `ln -sfn ../../data/送标/adas datasets/adas`）。

---

## 本机直跑（不用 Docker 跑 Platform）

```bash
pip install -r requirements.txt
bash scripts/init_after_clone.sh
bash scripts/run_local.sh
```

- Job 默认 `AS_JOB_EXECUTOR=thread`（无需 Redis）
- 无 PostgreSQL 时自动回退 SQLite（`manifests/platform.db`）
- 标注功能需 CVAT 可达（`CVAT_HOST`）

仅基础设施用 Docker：

```bash
docker compose up -d postgres redis
bash scripts/run_local.sh
```

---

## 认证（飞书 + PostgreSQL）

```bash
cp manifests/feishu.env.example manifests/feishu.env
# 填入 FEISHU_APP_ID / FEISHU_APP_SECRET / AS_JWT_SECRET
```

| 角色 | 权限 |
|------|------|
| admin | 全部 + 用户管理 |
| reviewer | 审核批准/驳回 |
| engineer | 送标开标、任务分配、build/train |
| labeler | 我的标注、CVAT 画布保存 |
| viewer | 只读 |

**飞书任务分配** 需应用权限：`contact:contact:readonly_as_app`、`im:message:send_as_bot` 等（详见 `docs/HANDOVER.md`）。

---

## CLI 示例

```bash
python as.py pending
python as.py add dms dam --src /path/to/batch ...
python as.py train dms dam --track local
python as.py train dms dam --track platform
```

---

## 维护者

### 从 workspace 刷新内嵌代码

```bash
bash scripts/vendor_workspace.sh
git add algorithms/ datasets/ manifests/repo_layout.json
git commit -m "chore: refresh vendored algorithm scaffolds"
```

### 同步到训练服务器

```bash
bash scripts/sync_to_server.sh user@host:/opt/HSAP
bash scripts/sync_to_server.sh user@host:/opt/HSAP --code-only
```

### 推送到 Git 远端

```bash
cd HSAP
git status   # 确认无 .env、feishu.env、node_modules、*.pt、送标图像
git push origin main
```

远端：`https://git.sanyele.com/ChengFang.LU/HSAP.git`

---

## 更多文档

| 文档 | 说明 |
|------|------|
| [docs/HANDOVER.md](docs/HANDOVER.md) | **项目交接**：架构、API、运维、排障 |
| [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) | 开发指南 |
| [docs/DATA_LAKE_CHECKLIST.md](docs/DATA_LAKE_CHECKLIST.md) | 数据湖检查清单 |

---

## Job 执行模式

| `AS_JOB_EXECUTOR` | 行为 |
|-------------------|------|
| `worker` | Docker 默认：API 入队 Redis，worker 执行 |
| `thread` | 本机调试：API 进程内线程执行 |

GPU 训练机：

```bash
PYTHONPATH=platform AS_JOB_EXECUTOR=worker python scripts/worker.py
```

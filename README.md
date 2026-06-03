# HSAP — Huaxu Sentinel Active Safety Platform

**华胥 Sentinel 主动安全算法迭代平台**（HSAP）：卡车主动安全（DMS / Lane / ADAS）算法迭代平台，含 **Web UI + API + 审核 + Job 队列 + 算法适配器**。

克隆本仓库即可运行平台；**算法源码与数据集脚手架已内嵌**，无需依赖本地软链。大文件（图像、训练权重）通过外部 `workspace` 挂载或自行 rsync。

---

## 仓库结构

```text
HSAP/                          # 建议 clone 目录名
├── as.py / workflow.registry.yaml
├── platform/
│   ├── as_platform/           # FastAPI 后端（Python 包名保留 as_platform）
│   └── web/                   # React (Vite) 前端
├── algorithms/
│   ├── dms_yolo/code/         # DMS YOLO26 训练代码（内嵌）
│   └── lane_ufld/code/        # Lane UFLD 代码（内嵌）
├── datasets/
│   ├── dms/                   # DMS 配置/脚本脚手架
│   └── lane/                  # Lane 列表与脚本脚手架
├── scripts/
├── docker-compose.yml / Dockerfile
└── manifests/
```

| 内容 | 是否在 Git 中 | 说明 |
|------|---------------|------|
| 平台 + 前端 + 适配器 | ✅ | 直接提交 |
| 算法 Python 源码 | ✅ | `scripts/vendor_workspace.sh` 同步 |
| 数据集 yaml/脚本 | ✅ | 不含图像 |
| 图像 / 视频 / 权重 | ❌ | `.gitignore` 排除；用 workspace 挂载 |

---

## 快速开始（Docker，推荐）

**依赖：** Docker 20+、Docker Compose v2

```bash
git clone <你的仓库 URL> HSAP
cd HSAP

bash scripts/init_after_clone.sh   # 生成 .env / feishu.env
bash scripts/dev_up.sh             # 或: make up
```

| 服务 | 地址 |
|------|------|
| 平台 UI + API | http://127.0.0.1:8787 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

```bash
make logs      # platform / worker 日志
make down      # 停止
make dev       # 额外启动 Vite 热更新 :5173
```

**开发登录：** 默认 `manifests/feishu.env` 中 `AS_DEV_AUTH=true`，无需飞书即可登录。

**改 HSAP 前端后（源码在 `platform/web/`）：** 须执行 `bash scripts/build_web.sh` 并 `docker compose restart platform`，否则 8787 仍为旧静态包。

---

## 本机直跑（不用 Docker 跑 Platform）

```bash
pip install -r requirements.txt
bash scripts/init_after_clone.sh
bash scripts/run_local.sh
```

- Job 默认 `AS_JOB_EXECUTOR=thread`（无需 Redis）
- 无 PostgreSQL 时自动回退 SQLite（`manifests/platform.db`）

仅基础设施用 Docker：

```bash
docker compose up -d postgres redis
bash scripts/run_local.sh
```

---

## 外部 workspace（大文件数据）

若你有 monorepo 布局 `DATA/workspace/`（含 DMS 图像、Lane 数据等）：

```bash
# .env 中设置
AS_WORKSPACE_ROOT=/path/to/DATA/workspace

bash scripts/setup_links.sh
docker compose up -d --build
```

---

## 维护者：从 workspace 刷新内嵌代码

```bash
bash scripts/vendor_workspace.sh
git add algorithms/ datasets/ manifests/repo_layout.json
git commit -m "chore: refresh vendored algorithm scaffolds"
```

同步到训练服务器：

```bash
bash scripts/sync_to_server.sh user@host:/opt/HSAP
bash scripts/sync_to_server.sh user@host:/opt/HSAP --code-only
```

---

## 上传到 Gitea / GitHub

1. 创建空仓库，名称：**`HSAP`**
2. 本地：

```bash
cd HSAP
git init
git add .
git status   # 确认无 .env、feishu.env、node_modules、*.pt 等大文件
git commit -m "feat: initial HSAP platform"
git remote add origin https://gitea.example.com/ChengFang.LU/HSAP.git
git branch -M main
git push -u origin main
```

3. **Push 前检查：**

```bash
git check-ignore -v manifests/feishu.env .env platform/web/node_modules
find . -type l ! -path './platform/web/node_modules/*' | wc -l   # 应为 0
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
| engineer | 提交 build/train |
| labeler | 目录/批次登记 |
| viewer | 只读 |

---

## CLI 示例

```bash
python as.py pending
python as.py add dms dam --src /path/to/batch ...
python as.py train dms dam --track local
python as.py train dms dam --track platform
```

---

## 更多文档

- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)
- [docs/DATA_LAKE_CHECKLIST.md](docs/DATA_LAKE_CHECKLIST.md)

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

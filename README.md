# aegis-lab

**主动安全算法实验平台** — 从数据湖送标、CVAT 标注、审核发版到 DMS / ADAS / Lane 训练流水线，一套 Docker 拉起。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 是什么

aegis-lab 面向 **商用车主动安全** 场景的算法迭代：舱内 DMS、前向 ADAS（2D 检测 / 3D Cuboid）、车道线分割等。  
把「批次进湖 → 登记台账 → 开标标注 → 质检导出 → 训练打包」串成可复现的工作流，适合个人实验与小团队联调。

**一条命令** 启动 Web 平台 + 内置 CVAT 标注引擎 + PostgreSQL / Redis，无需单独部署标注服务或再 clone [opencv/cvat](https://github.com/opencv/cvat) 完整工程。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **批次台账** | 扫描数据湖 inbox、NAS 送标登记、业务线（DMS / ADAS 2D·3D / Lane） |
| **送标工作台** | 批次开标、软删除、同步磁盘索引 |
| **CVAT 标注** | 2D 框、关键点、3D Cuboid、车道线折线；iframe 嵌入，平台统一登录 |
| **质检 / 导出** | 标注回写数据湖，导出 YOLO / quaternion JSON / 车道线 GT |
| **车队地图** | 实时 GPS、Leaflet 底图、T-Box 轨迹演示 |
| **Job 队列** | 训练 build、数据 ingest 等异步任务 |
| **权限** | 飞书 OAuth + 开发登录；RBAC 角色 |

---

## 架构

```text
┌─────────────────────────────────────────────────────────┐
│  Web UI (React)          http://127.0.0.1:8788          │
│  FastAPI + Worker        PostgreSQL / Redis             │
└───────────────────────────┬─────────────────────────────┘
                            │ REST / iframe
┌───────────────────────────▼─────────────────────────────┐
│  CVAT (Traefik :8081)                                   │
│    ui:dev  +  cvat-server (官方镜像 + vendor 补丁)       │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  数据湖 (volume 挂载)                                    │
│    datasets/{dms,adas,lane}/inbox/{task}/{batch}/       │
└─────────────────────────────────────────────────────────┘
```

CVAT 定制补丁在 `vendor/cvat/patches/`（iframe 嵌入、内网 no_auth），已打入 `aegis-lab-cvat-server` 镜像。  
详见 [docs/CVAT_INTEGRATION.md](docs/CVAT_INTEGRATION.md)。

---

## 快速开始

### 环境要求

- Docker 24+ 与 Compose v2
- 8GB+ 内存（含 CVAT 全家桶）
- 可选：外部 `workspace` / `data` 目录挂载真实训练数据

### 启动

```bash
git clone https://github.com/Weeknd0214/aegis-lab.git
cd aegis-lab
cp .env.example .env
cp manifests/feishu.env.example manifests/feishu.env   # 按需改飞书 / 开发登录

docker compose up -d --build
# 或
make up
```

| 服务 | 地址 |
|------|------|
| **平台** | http://127.0.0.1:8788 |
| **CVAT 画布** | http://127.0.0.1:8081（由平台 iframe 嵌入） |
| PostgreSQL | `localhost:5433` |
| Redis | `localhost:6380` |

首次登录：开启 `AS_DEV_AUTH` 时使用页面 **开发登录**；生产环境配置飞书应用见 `manifests/feishu.env.example`。

### 改前端后

```bash
bash scripts/build_web.sh
docker compose restart platform
```

---

## 数据湖 inbox 约定

大文件（图像、权重）**不进 Git**，通过目录挂载。样例布局见 `lake/lake_example/`。

| 业务 | 路径 | project | task |
|------|------|---------|------|
| DMS 舱内 | `datasets/dms/inbox/{task}/{batch}/` | `dms` | addw / ddaw / dam … |
| ADAS 2D | `datasets/adas/inbox/det_7cls/{batch}/` | `adas` | `det_7cls` |
| ADAS 3D | `datasets/adas/inbox/cuboid_7cls/{batch}/` | `adas` | `cuboid_7cls` |
| 车道线 | `datasets/lane/inbox/{batch}/` | `lane` | `lane_v1` |

`.env` 中可设置 `AS_DATA_LAKE_HOST` 指向宿主机数据根目录（默认 `../data`）。

---

## 仓库结构

```text
aegis-lab/
├── platform/
│   ├── as_platform/       # FastAPI 后端
│   └── web/               # React 前端 (Vite)
├── datasets/              # 任务 registry、标注 profile、ingest 脚本
├── algorithms/            # DMS YOLO、Lane UFLD 训练代码
├── lake/lake_example/     # inbox 落盘样例与 manifest
├── vendor/cvat/patches/   # CVAT 集成补丁（已纳入版本库）
├── docker/
│   └── cvat-server/       # 补丁 Dockerfile
├── docker-compose.yml     # 平台 + CVAT 单文件编排
├── scripts/               # build_web、docker_push、dev_up …
└── docs/                  # CVAT 接入、运维、E2E 说明
```

---

## Docker 镜像（可选）

预构建镜像发布在 GitHub Container Registry：

| 镜像 | 说明 |
|------|------|
| `ghcr.io/weeknd0214/aegis-lab-platform` | API + 前端静态资源 |
| `ghcr.io/weeknd0214/aegis-lab-cvat-server` | CVAT Server + 补丁 |

```bash
# 构建并推送（维护者）
docker login ghcr.io
bash scripts/docker_push.sh

# 使用预构建镜像
docker compose pull
docker compose up -d
```

---

## 常用命令

```bash
make up          # 启动全套服务
make down        # 停止
make logs        # 查看平台与 CVAT 日志
make health      # 探测 API
make push        # 构建并推送 GHCR 镜像
```

重置标注相关数据库（保留账号）：

```bash
bash scripts/reset_labeling.sh
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/CVAT_INTEGRATION.md](docs/CVAT_INTEGRATION.md) | CVAT 如何接入、不必 clone opencv/cvat |
| [docs/HANDOVER.md](docs/HANDOVER.md) | 模块与 API 交接说明 |
| [lake/lake_example/README.md](lake/lake_example/README.md) | 各业务线 inbox 样例 |
| [vendor/cvat/README.md](vendor/cvat/README.md) | CVAT 补丁说明 |

---

## 技术栈

- **后端**：Python 3.11、FastAPI、SQLAlchemy、PostgreSQL、Redis
- **前端**：React 18、Vite、Tailwind CSS
- **标注**：CVAT（Docker 官方镜像 + 定制补丁）
- **地图**：Leaflet、高德 / OSM 瓦片
- **训练**：Ultralytics YOLO、UFLD 车道线（`algorithms/`）

---

## 说明

- 本仓库为 **实验 / 个人开发** 用途；生产部署请自行更换密钥、关闭 `AS_DEV_AUTH`、配置 HTTPS 与备份策略。
- 数据集与模型权重通过 volume 挂载，克隆仓库后需自行准备数据或复制 `lake/lake_example` 样例到 inbox。

---

## License

MIT — 详见 [LICENSE](LICENSE)（若未包含，以仓库根目录实际文件为准）。

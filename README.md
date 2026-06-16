# aegis-lab

> **Personal sandbox for active-safety ML operations** — not affiliated with any company production deployment.

个人主动安全算法实验沙箱：送标数据湖 inbox、CVAT 标注、车队实时地图、审核与 Job 队列，覆盖 **DMS / ADAS / Lane** 训练流水线。由内部 HSAP 平台复制而来，Docker 项目名与端口已独立，可与原 HSAP 并存。

---

## Repository Description（Git 远程仓库简介）

**English（推荐填 Git Description）：**

```text
Personal ML ops sandbox: data-lake inbox, CVAT labeling, fleet GPS map, and DMS/ADAS/Lane training pipelines. Not for production.
```

**中文：**

```text
个人主动安全算法实验环境：数据湖送标、CVAT 标注、车队地图、DMS/ADAS/车道线训练流水线。非生产部署。
```

---

## 与 HSAP 的区别

| 项 | aegis-lab | 原 HSAP |
|----|-----------|---------|
| 用途 | 个人开发备份 / 试验 | 公司主平台 |
| 默认 UI 端口 | **8788** | 8787 |
| CVAT 端口 | **8081** | 8080 |
| Docker 项目名 | `aegis-lab` | `hsap` |
| 容器前缀 | `aegis-lab-*` | `hsap-*` |
| 大数据 | 未复制 `datasets/dms/packs`、`inbox` | 含完整数据 |

数据仍通过 volume 挂载共享：`../data`、`../workspace`（`adas` / `lane` 软链不变）。

---

## 快速启动

```bash
cd ~/DATA/aegis-lab
docker compose up -d --build
# 或
make up
```

| 服务 | 地址 |
|------|------|
| 平台 UI | http://127.0.0.1:8788 |
| CVAT | http://127.0.0.1:8081 |

**单文件 compose**：平台 + CVAT 已合并进 `docker-compose.yml`（不再需要 `-f docker-compose.cvat.yml`）。

---

## Docker 镜像（GHCR）

推送到 `ghcr.io/weeknd0214`（需 `docker login ghcr.io`）：

```bash
bash scripts/docker_push.sh
# 或 make push
```

| 镜像 | 内容 |
|------|------|
| `aegis-lab-platform` | FastAPI + 已 build 的前端静态包 |
| `aegis-lab-cvat-server` | 官方 `cvat/server:dev` + **vendor/cvat/patches** 补丁 |

远端拉取部署：

```bash
docker compose pull
docker compose up -d
```

CVAT **UI** 仍用官方 `cvat/ui:dev`（Docker Hub）；定制代码在 `vendor/cvat/patches/`，详见 **[docs/CVAT_INTEGRATION.md](docs/CVAT_INTEGRATION.md)**（**不必**再下载 opencv/cvat 工程）。

---

## 目录结构

与 HSAP 相同，详见 `docs/HANDOVER.md`。核心路径：

```text
aegis-lab/
├── platform/          # FastAPI + React
├── datasets/          # 配置与脚本（大文件不随仓）
├── algorithms/        # DMS / Lane 训练代码
├── lake/lake_example/ # inbox 落盘样例
├── docker-compose.yml
└── scripts/
```

---

## 说明

- 容器内代码挂载点仍为 `/data/hsap`（与镜像 Dockerfile 一致），仅宿主机目录名为 `aegis-lab`。
- 勿将本仓当作公司官方发布版本；合并能力回主仓前请在 HSAP 侧验证。

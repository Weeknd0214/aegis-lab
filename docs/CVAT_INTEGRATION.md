# CVAT 接入指南（aegis-lab）

clone 本仓库后 **不需要** 再去下载 [opencv/cvat](https://github.com/opencv/cvat) 完整工程。  
标注能力通过 **Docker 镜像 + 少量补丁** 接入，平台用 HTTP API 调 CVAT。

---

## 架构一览

```text
浏览器
  └─ aegis-lab 平台 :8788（React + FastAPI）
        │  开标 / 同步标注 / iframe 嵌入
        ▼
     CVAT 网关 :8081（Traefik）
        ├─ cvat/ui:dev          ← 官方 UI 镜像（Docker Hub）
        └─ aegis-lab-cvat-server ← 官方 server + vendor/cvat/patches
              ├─ cvat_db (Postgres)
              ├─ Redis / ClickHouse / OPA
              └─ workers (import/export/annotation)
```

| 你 clone 的 aegis-lab 里有什么 | 作用 |
|-------------------------------|------|
| `vendor/cvat/patches/*.py` | 允许 iframe、no_auth，与平台单点登录配合 |
| `docker/cvat-server/Dockerfile` | 把补丁打进 CVAT Server 镜像 |
| `docker-compose.yml` | 一键拉起平台 + CVAT 全套服务 |
| `platform/as_platform/labeling/cvat_client.py` 等 | 平台侧：创建 Task、上传图、拉标注 |

| 不在本仓库里的 | 从哪来 |
|----------------|--------|
| CVAT 完整源码 | 不需要；用镜像 `cvat/server:dev` / `cvat/ui:dev` |
| 预构建补丁镜像（可选） | `ghcr.io/weeknd0214/aegis-lab-cvat-server` |

---

## 新机器上怎么跑（最常见）

```bash
git clone git@github.com:Weeknd0214/aegis-lab.git
cd aegis-lab
cp .env.example .env
docker compose up -d --build
```

1. Compose 会从 Docker Hub 拉 `cvat/ui:dev` 等基础镜像。  
2. 若 GHCR 上已有 `aegis-lab-cvat-server`，执行 `docker compose pull` 可跳过本地构建 CVAT Server。  
3. 否则本地根据 `docker/cvat-server/Dockerfile` 构建（自动 COPY `vendor/cvat/patches/`）。  
4. 平台环境变量 `CVAT_HOST` 指向容器内 `http://aegis-lab-cvat-server:8080`，`CVAT_PUBLIC_URL` 为浏览器访问的 `http://127.0.0.1:8081`。

**无需** 再 `git clone opencv/cvat`。

---

## 平台如何「接上」CVAT（代码层面）

1. **开标**（创建标注任务）  
   `labeling/service.py` → `cvat_client.create_task()` → CVAT REST API  

2. **标注页**  
   `AnnotationPage` iframe 加载 `CVAT_PUBLIC_URL` 下的 Job 页面  

3. **同步回数据湖**  
   `cvat_client` 拉 Job 标注 → 写入批次 `labels/ls_annotations/`  

4. **标签 schema**  
   `labeling/cvat_config.py` + `datasets/labeling.registry.yaml` 按 DMS/ADAS/Lane 自动生成 CVAT labels  

补丁保证：CVAT 不强制独立登录，且允许被平台 `:8788` iframe 嵌入。

---

## 三种部署方式对比

| 方式 | 命令 | 适用 |
|------|------|------|
| **A. 全 compose 构建** | `docker compose up -d --build` | 本机开发，改平台代码 |
| **B. 拉 GHCR 镜像** | `docker compose pull && docker compose up -d` | 新机器快速部署 |
| **C. 仅改 CVAT 补丁** | 改 `vendor/cvat/patches/` → `docker compose build cvat_server` | 调 iframe/鉴权行为 |

CVAT UI 始终用官方 `cvat/ui:dev`；一般 **不必** 自编译 CVAT 前端。

---

## 若你要改 CVAT 本体（高级，通常不需要）

只有当你需要改 CVAT **核心功能**（而非补丁）时，才需要 fork [opencv/cvat](https://github.com/opencv/cvat)：

1. 在 CVAT 工程里改代码并 `docker compose build` 出自定义 `cvat/server` 镜像  
2. 把 `vendor/cvat/patches/` 合并进你的 CVAT 分支，或继续用 Dockerfile COPY 覆盖  
3. 在 aegis-lab 的 `docker-compose.yml` 里把 `AEGIS_CVAT_IMAGE` 改成你的镜像名  

日常标注流程（2D 框 / 3D cuboid / 车道线）**现有补丁 + 官方镜像即可**。

---

## 环境变量

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `CVAT_HOST` | `http://aegis-lab-cvat-server:8080` | 平台容器访问 CVAT（内网） |
| `CVAT_PUBLIC_URL` | `http://127.0.0.1:8081` | 浏览器 / iframe 地址 |
| `CVAT_PORT` | `8081` | 宿主机映射 CVAT 网关端口 |
| `AEGIS_CVAT_IMAGE` | `ghcr.io/weeknd0214/aegis-lab-cvat-server:latest` | 带补丁的 Server 镜像 |

---

## 推送镜像到 GHCR

```bash
docker login ghcr.io
bash scripts/docker_push.sh
```

会构建并推送 `aegis-lab-platform` 与 `aegis-lab-cvat-server`（补丁已内置）。

---

## 故障排查

| 现象 | 检查 |
|------|------|
| 标注页空白 | `curl http://127.0.0.1:8081` 是否通；`docker compose ps` 中 cvat_* 是否 healthy |
| iframe 被拒绝 | 补丁 `base.py` 是否生效；是否用了 `aegis-lab-cvat-server` 镜像 |
| 平台报 CVAT 不可用 | `docker compose logs platform` 看 `CVAT_HOST` 连通性 |
| 首次启动慢 | CVAT 需拉多个镜像（Postgres/ClickHouse/Redis），属正常 |

更多运维见 `docs/HANDOVER.md` 与 `vendor/cvat/README.md`。

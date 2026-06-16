# CVAT 集成说明

aegis-lab **不包含** CVAT 完整源码（体量过大）。集成方式为：

| 组件 | 来源 |
|------|------|
| CVAT Server / Worker | 官方镜像 `cvat/server:dev`，或本仓构建的 `ghcr.io/weeknd0214/aegis-lab-cvat-server` |
| CVAT UI | 官方镜像 `cvat/ui:dev` |
| **定制补丁** | 本目录 `patches/`（已纳入 Git） |

## 补丁作用

- `base.py` — 允许 iframe 嵌入、CORS、关闭多余鉴权入口
- `no_auth.py` / `no_auth_middleware.py` — 内网 no_auth 模式（由 HSAP 平台统一登录，CVAT 不单独要账号）

## 部署方式

1. **推荐** — `docker compose up -d --build`：用 `docker/cvat-server/Dockerfile` 构建，补丁已打进镜像  
2. **拉 GHCR** — `docker compose pull` 使用 `ghcr.io/weeknd0214/aegis-lab-cvat-server`  
3. **不必** clone [opencv/cvat](https://github.com/opencv/cvat) 完整工程

完整接入说明见 **[docs/CVAT_INTEGRATION.md](../../docs/CVAT_INTEGRATION.md)**。

UI 仍用 Docker Hub 的 `cvat/ui:dev`；Server/Worker 使用带补丁的镜像。

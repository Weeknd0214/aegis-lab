# HSAP 飞书集成（内网开发说明）

操作手册：[FEISHU_BITABLE_OPS.md](./FEISHU_BITABLE_OPS.md)

## 架构

- **入站**：无 Webhook（飞书云访问不到内网）
- **出站**：`tenant_access_token` 调用 Bitable API 回写记录
- **轮询**：`FEISHU_BITABLE_SYNC_INTERVAL_SEC`（默认 120s）或 `POST /api/v1/integrations/feishu/bitable/sync`

## 模块

| 路径 | 说明 |
|------|------|
| `platform/as_platform/integrations/feishu_bitable.py` | API 客户端、列映射 |
| `platform/as_platform/integrations/feishu_bitable_sync.py` | HSAP→表同步 |
| `platform/as_platform/integrations/feishu_bitable_ingest.py` | 待落盘→analyze→promote |
| `platform/as_platform/integrations/feishu_notify.py` | 群文本通知（可选） |
| `platform/as_platform/jobs/feishu_bitable_sync.py` | `run_sync_cycle()` 后台轮询 |
| `platform/as_platform/api/feishu_routes.py` | status / sync / ingest / backfill-hints |

## 权限

- `POST .../sync`、`GET .../backfill-hints`：需 `write:labeling_assign` 或 `*`

## Phase

- **A**（默认）：回写 Inbox路径、HSAP进度、活动ID、状态、链接  
- **B**：`FEISHU_BITABLE_AUTO_INGEST=1` 时轮询「待落盘」→ analyze → promote；或 `POST .../bitable/ingest`

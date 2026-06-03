# 平台批次台账与审批入湖

主路径已替代飞书多维表格 API 拉取。飞书表仅作可选人工备忘（`FEISHU_BITABLE_SYNC_ENABLED=0`）。

相关文档：[LABELING_SOP.md](./LABELING_SOP.md) §5.2 · Pilot：[PILOT_BATCH.md](./PILOT_BATCH.md)

## 角色分工

| 角色 | 操作 |
|------|------|
| 协调员（labeler） | HSAP → **批次台账**：新建/编辑申请 → **提交审批** |
| 数据平台（reviewer） | **审核管理**：动作「数据送标入湖」→ 通过/驳回 |
| 标注协调 | 入湖后在 **送标工作台 → 待送标** 开 Campaign |

权限：`write:delivery_submit`（提交）、`read:deliveries`（查看台账）、`write:approval_review`（批准入湖）。

## 状态说明

| 状态 | 含义 |
|------|------|
| `draft` | 草稿，可编辑 |
| `pending_review` | 已提交，待审核 |
| `rejected` | 驳回，可改后再提交 |
| `ingesting` | 审批通过，Job 执行 analyze + promote |
| `in_lake` | 已入 inbox，可送标 |
| `ingest_failed` | 入湖失败，见 `error_message` |

## 表单字段（对齐原飞书列）

- **项目 / 任务 / 子模式 / 批次名**：与 inbox 规则一致；单层任务 `mode` 可空；**批次名 ≠ 任务名**。
- **数据路径**：容器内或 NAS **绝对路径**，提交前须存在且含图像。
- **来源类型、车辆/场景、采集起止、预估张数、备注**：可选。

API：`GET/POST/PATCH /api/v1/deliveries`，`POST /api/v1/deliveries/{id}/submit`。

## 与 Pilot `20260525_pilot` 联调

1. 确认 inbox 已有数据：`/data/hsap/datasets/dms/inbox/addw/20260525_pilot`（见 [PILOT_BATCH.md](./PILOT_BATCH.md)）。
2. **批次台账** 新建：项目 `dms`，任务 `addw`，批次 `20260525_pilot`，路径填上列目录。
3. **提交审批** → **审核管理** 批准 → 状态 `in_lake`，`inbox_path` 回写。
4. **送标工作台** 待送标可见该批次 → 开始标注。

演示已入湖批次：可在库中直接将记录标为 `in_lake` 并填 `inbox_path`，跳过审批。

## 部署注意

- 升级后重启 platform/worker：`docker compose restart platform worker`，以便 `create_all` 创建 `batch_deliveries` 并种子权限。
- 飞书同步保持关闭：`manifests/feishu.env` 中 `FEISHU_BITABLE_SYNC_ENABLED=0`。

## 前端构建（必做）

HSAP 页面来自 Label Studio 工程编译后的静态包，**改 TSX 后必须重建**才会在 `http://127.0.0.1:8787` 生效：

```bash
bash /home/chengfanglu/DATA/HSAP/scripts/build_hsap_ls_ui.sh
cd /home/chengfanglu/DATA/HSAP && docker compose restart platform
```

浏览器访问后请 **强制刷新**（Ctrl+Shift+R）。开发热更新可选用：`docker compose --profile dev up`（见 `docker-compose.yml` 注释）。

## UI 闭环路径（Phase A）

| 步骤 | 页面 | 说明 |
|------|------|------|
| 1 | 批次台账 `/deliveries` | 列表有进度条；提交后状态「待审核」 |
| 2 | 审核管理 `/audit` | 动作「数据送标入湖」；详情页可看待审 Job 与 inbox_path |
| 3 | 送标工作台 `/labeling` | 待送标见批次；已入湖台账显示申请 ID |
| 4 | 进行中标注 | 开 Campaign / 画布 |

协调员登录默认进入 **批次台账**；审核员默认进入 **审核管理**（见 `defaultLanding.ts`）。

## 验收清单

- [ ] 协调员创建并提交申请
- [ ] 审核员看到「数据送标入湖」并批准，Job 成功
- [ ] `GET /api/v1/deliveries` 显示 `in_lake` 且 `inbox_path` 正确
- [ ] 送标工作台可见批次并可开 Campaign
- [ ] 驳回后可编辑再提交

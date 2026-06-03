# HSAP 验收与缺口报告

生成方式：`bash HSAP/scripts/smoke_platform_api.sh` + 对照 [BROWSER_QA_CHECKLIST.md](BROWSER_QA_CHECKLIST.md)

**最近 smoke：** 通过（`ALL_OK`），health / labeling batches(7) / fleet live(3) / export-jobs / bootstrap / export / ml-predict 均正常。

## API 自动化

| 项 | 状态 | 备注 |
|----|------|------|
| Health + DB/Redis | 通过 | |
| labeling/batches | 通过 | 7 条（含 registry_only 占位批次） |
| dam bootstrap | 通过 | `dam_15cls.xml` 已写入 campaign |
| export / ml-predict | 通过 | ExportJob 与 jobs 队列联动 |
| fleet map-config / live | 通过 | 需 `AS_FLEET_MAP_ENABLED=1` |

## 浏览器（需人工勾选）

见 [BROWSER_QA_CHECKLIST.md](BROWSER_QA_CHECKLIST.md)。自动化无法覆盖 UI 布局与瓦片加载。

## 已确认缺口

| 缺口 | 影响 | 缓解 |
|------|------|------|
| inbox **无样例图片** | `tasks` 为空，画布无法 E2E 框选保存 | 往 `datasets/dms/inbox/dam/batch_0516/` 放 jpg；或 reseed 演示批次 |
| export worker 占位 | job `message` 为记录型，未真跑 YOLO 转换 | 见 runner `labeling_export`；后续对接 `as.py build` |
| ML 预标 | 已停用 | 无 UI / 无 `POST .../ml/predict` |
| 无 vendor 回传 | 第三方离线标无法导入 | 本里程碑新增 `import-vendor` API |
| 无独立 Export/ML 页 | 仅在 Campaign 行操作 | 本里程碑新增 `/labeling/export`、`/labeling/ml` |
| 车队无 SSE | 15s 轮询 | 本里程碑新增 `/fleet/stream` |
| 数据入湖 staging | checklist A～E 未全实现 | 见 [DATA_LAKE_GAP.md](DATA_LAKE_GAP.md) |

## 建议复测命令

```bash
bash HSAP/scripts/smoke_platform_api.sh
bash HSAP/scripts/smoke_labeling_api.sh
cd HSAP && docker compose up -d --build platform
```

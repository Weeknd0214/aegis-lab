# HSAP UI 浏览器验收记录

API 自动化：`bash HSAP/scripts/smoke_platform_api.sh`（含 labeling + fleet health）

## 自动化结果（最近一次）

| 检查项 | 命令/路径 | 预期 |
|--------|-----------|------|
| Health | `GET /api/v1/health` | `status: ok` |
| 标注批次 | `GET /api/v1/labeling/batches` | `items.length >= 1`（当前约 7） |
| Bootstrap / export / ml | `smoke_platform_api.sh` | exit 0，`ALL_OK` |
| 车队配置 | `GET /api/v1/fleet/map-config` | `enabled: true`（需 `AS_FLEET_MAP_ENABLED`） |
| 车队 live | `GET /api/v1/fleet/live` | `vehicles.length >= 1`（演示约 3） |

详细缺口见 [QA_GAP_REPORT.md](QA_GAP_REPORT.md)。

## 浏览器手动清单

- [ ] 登录 `http://127.0.0.1:8787`（强刷 Ctrl+Shift+R）
- [ ] **送标工作台**：Tab 待送标/标中/待入库/上传入湖；待送标「开始标注」；待入库选 pack 提交审核；上传 promote 后回待送标；见 [LABELING_SOP.md](LABELING_SOP.md)
- [ ] **标注任务**：可见 `dam/batch_0516` 等批次；表头有 **进度**、**分包** 列；展开行可 **均分未分配任务**
- [ ] **送标工作台·标中**：左侧列表有进度/分包列；右侧 **任务分配** 面板（协调员）
- [ ] **分包验收**：协调员对 batch 均分给 2 人 → 各员画布 task 数约一半、互不重叠；A 保存后 A 的 completed +1
- [ ] **批次台账**：导航「批次台账」可见；新建申请（项目/任务/批次名/数据路径）→ 提交审批；`GET /api/v1/deliveries` 状态 `pending_review`
- [ ] **审批入湖**：审核管理出现「数据送标入湖」，详情展示结构化字段（非仅 JSON）；批准后 Job 成功，台账 `in_lake` 且 `inbox_path` 正确
- [ ] **送标衔接**：送标工作台待送标可见该批次；驳回后可编辑再提交（见 [BATCH_DELIVERY_OPS.md](BATCH_DELIVERY_OPS.md)）
- [ ] （可选）飞书表仅人工备忘：`FEISHU_BITABLE_SYNC_ENABLED=0`，不依赖 `bitable/sync`
- [ ] **画布**：`dam_15cls.xml`；inbox 有图时可保存；内部标注员顶栏 **我的进度**；协调员可切 **全部/仅我的**
- [ ] **Jobs**：导出后出现 `labeling_export`
- [ ] **审核**：列表、详情、lightbox；缩略图含 YOLO 叠加框
- [ ] **车队**：瓦片可见；地图左、CRUD 右（宽屏）；重置演示后有蓝点
- [ ] **训练**：发起 + 详情 + registry
- [ ] **数据目录**：视角「训练包」下先选 `dms_v1` 再选任务（dam/addw_face 等）；「采集批次」下选任务再选 0516 批次；两种视角图表数值可不同；`dms_v1`+`dam` 刷新后框宽高散点非空

## 已知缺口

- **标注 tasks 为空**：inbox 目录无图片时正常；往 registry inbox 路径放样例 jpg 后再测
- **瓦片灰屏**：设置 `AS_MAP_TILE_PROVIDER=osm` 或配置 `AS_AMAP_KEY`；UI 已支持瓦片失败自动切 OSM

## 环境变量（车队地图）

```bash
AS_FLEET_MAP_ENABLED=1
AS_MAP_TILE_PROVIDER=gaode   # 或 osm
AS_AMAP_KEY=               # 高德 key，可选
``` 

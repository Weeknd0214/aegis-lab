# 送标工作台 SOP

本文说明 HSAP 中 **送标** 的含义、应投递的数据形态、人员协作方式，以及与数据入湖路径的分工。配套实现见送标工作台 UI 与 `POST /api/v1/data/candidates/{id}/promote-inbox`。

## 1. 送标是什么

**送标** = 把一批数据纳入标注流水线，并（通常）**开启标注活动（Campaign）**，阶段变为 `out_for_labeling`（送标中）。

| 阶段 | 含义 | 目录特征（DMS） |
|------|------|-----------------|
| `raw_pool` | 待标注原图 | 有 `images/`，无 `labels/` |
| `out_for_labeling` | 送标中 | 已 open Campaign |
| `returned` | 回传待入库 | 有 `images/` + `labels/`（YOLO txt） |
| `ingested` | 已入库 | 已进入 pack/sources 或 Lane gt |

**登记 meta**（`更多操作` 内）只写入 `batch.meta.yaml`，**不等于**已送标。

### 1.1 口语里的「送标数据」

通常指 **还没标完** 的原图批次（`raw_pool`），即 inbox 里只有 `images/`、没有 `labels/`。标完后进入 `returned`（待入库），不再算「待送标」。

## 2. 送标工作台怎么用（协调员）

侧栏 **送标工作台**（`/labeling`）负责 **收件 + 派单**；**进行中标注**（`/labeling/campaigns`）负责画布、导出、外协回传。不要两页重复找「进入标注」。

| Tab | 对应阶段 | 你要做的事 |
|-----|----------|------------|
| **待送标**（默认） | `raw_pool` | 选批次 → **开始标注** / **开始并指派** |
| **标中** | `out_for_labeling` | **继续标注**；协调员在此 **均分未分配任务**（见 §5.1） |
| **待入库** | `returned` | 选训练包 → **提交入库审核** |
| **上传入湖** | 入湖候选 | 上传 ZIP → 分析完成 → **送入 inbox**（自动切回待送标） |

页顶 **协调员三步**：进数据 → 开始标注 → 回传后提交入库。KPI 卡片可点击，与 Tab 联动。

```text
落盘 inbox 或 上传入湖
    → 待送标 Tab：开始标注
    → 进行中标注：画布 / 外协回传
    → 待入库 Tab：提交入库审核
    → 审核通过 → build → 数据目录
```

## 3. 两条数据路径（勿混淆）

### 路径 A：inbox 落盘（主送标路径）

运维/脚本将批次放到约定目录 → 刷新工作台 → **待送标** Tab 出现该批次。

### 路径 B：页面上传 ZIP（入湖候选）

工作台 **上传入湖** Tab → `manifests/lake/uploads/` → 分析完成 → **送入 inbox** → 自动出现在 **待送标**。

路径 B 不会在上传瞬间出现在批次表；必须 **分析完成 + 送入 inbox**（或手工落盘路径 A）。

## 4. 应投递什么

### 4.1 DMS 检测（如 `dam` + `batch_0516`）

**待标注（原图池）**

```text
datasets/dms/inbox/dam/batch_0516/
  images/train/    # 或 images/
    *.jpg
```

**外协/平台已标回传**

```text
<batch>/
  images/train/
  labels/train/
    # YOLO: class_id cx cy w h  (0~1)
```

任务 id 填 registry 中的 **`dam`**；0516/0417 是 **mode**，目录对应 `inbox/dam/batch_0516`（见 [datasets.registry.yaml](../datasets/dms/datasets.registry.yaml)）。

### 4.2 DMS 人脸关键点（`addw_face`）

画布使用 `dms_pose.xml`：**face 检测框** + **37 个关键点**（`kp_00`–`kp_36`）。保存为 Label Studio JSON（`labels/ls_annotations/*.json`）；导出时转为 YOLO pose 行：

```text
0 <cx> <cy> <w> <h> <kpt0_x> <kpt0_y> <kpt0_v> ... <kpt36_x> <kpt36_y> <kpt36_v>
```

共 **116 字段**（`5 + 37×3`）。已标注点 `v=2`，未标注点 `0 0 0`。坐标：LS 为图像百分比 0–100，YOLO 为 0–1。

检测任务（`dam`/`addw`/`ddaw`）导出为 5 字段 YOLO detect 行，与 pose **共用** `export_ls_to_yolo.py`。

数据目录「框宽高散点」统计的是 **检测框宽高**，不是关键点坐标。

### 4.3 外协 ZIP

结构见 [VENDOR_RETURN.md](./VENDOR_RETURN.md)。在 **标注任务** 页对已有 Campaign **导入回传**，不要与送标工作台 ZIP 上传混用。

### 4.4 Lane（UFLD 分割 mask）

`project=lane`，任务 `lane_v1`。画布使用 **`lane_ufld_mask.xml`**：**BrushLabels 画笔** 沿每条车道线涂抹（`lane_1`～`lane_5`，对应 mask 像素值 2～6）。

标注保存为 Label Studio JSON（`labels/ls_annotations/*.json`）；导出时转为 UFLD 训练包：

```text
<batch>/
  images/...
  annotations/.../*.png    # 单通道 mask，0=背景，2~6=各车道线
  list/train_gt.txt        # 两列：images/...jpg annotations/...png
```

在 **进行中标注** 页点 **导出** 会运行 `export_ls_to_lane_gt.py`，并触发 `as.py build lane` 合并 active_packs 列表。依赖 **numpy**（与 Lane 训练环境一致）。

| 像素值 | 标签 |
|--------|------|
| 0 | 背景 |
| 2 | lane_1 |
| 3 | lane_2 |
| 4 | lane_3 |
| 5 | lane_4 |
| 6 | lane_5 |

详见 [LANE_LABELING_PLAN.md](./LANE_LABELING_PLAN.md) 与 [`workspace/lane`](../../workspace/lane/) 数据规范。

## 5. 人员分配与任务分包

| 角色 | 职责 |
|------|------|
| `labeler`（协调员） | 看待处理批次、送入 inbox、登记 meta、提交入库审核、**指派批次负责人**、**按人分包 task** |
| `internal_labeler` | 画布仅见 **分给自己的** task；顶栏显示「我的进度」 |
| `vendor_labeler` | 导入外协 ZIP（整包回传，不走分包表） |

**批次负责人**（`assigned_to_*`）表示本批 **主责协调人**；**分包**（`labeling_task_assignments`）按 **单张图 task_id** 分给内部标注员，二者并存。

**操作顺序**

1. 协调员：inbox 落盘或上传分析后 **送入 inbox**。
2. 送标工作台 **待送标**：选批次 → **开始标注**（open Campaign）→ 可选指派批次负责人。
3. **标中** Tab 或 **进行中标注**：协调员勾选标注员 → **均分未分配任务**。
4. 标注员：侧栏 **进行中标注** → 进入画布（默认 `assignee=me`）→ 保存后个人 `completed` +1。
5. 外协：**导入回传**（不走分包）。
6. 回传齐后：`returned` → **提交入库审核** → 审核批准 → build/ingest → **数据目录** 刷新。

### 5.1 任务分包与进度

| 概念 | 说明 |
|------|------|
| `total_tasks` | 批次 `images/` 下图片数（与画布 task 一致） |
| `completed_tasks` | `labels/ls_annotations/*.json` 中非空 `result` 数量 |
| `assigned_tasks` | 分包表行数；未分配部分仅协调员可标（默认） |
| 进度 API | `GET /api/v1/labeling/campaigns/{id}/progress` |
| 均分 | `POST .../assign-tasks` `{ "mode": "even", "user_ids": [...] }` |

协调员在 **进行中标注** 展开行，或 **送标工作台 → 标中** 右侧详情，可查看总进度、按人表并 **均分**。内部标注员对 **未分给自己** 的 task 保存会 **403**（默认禁止抢标）。

画布：协调员可切换 **全部任务 / 仅我的**；标注员仅见自己的分包列表。待入库 Tab 建议在 `completed === total` 时再提交（软提示）。

### 5.2 批次台账与审批入湖（主路径）

操作手册：[BATCH_DELIVERY_OPS.md](./BATCH_DELIVERY_OPS.md)

| 步骤 | HSAP（批次台账 + 审核） | 后续 |
|------|-------------------------|------|
| 登记 | **批次台账** 新建草稿（项目/任务/批次名/数据路径） | — |
| 入湖 | **提交审批** → 数据平台 **审核管理** 批准「数据送标入湖」 | Job：analyze → promote → inbox |
| 送标 | 状态 **已入湖** | 送标工作台 → 待送标 → 开始标注 |
| 标注 | — | 进行中标注 → 均分 → 画布 |
| 入库 | — | 回传 → 待入库 → 提交入库审核 → build |

- 新批次：**先填台账并审批入湖**，再开 Campaign；`批次名` 禁止与 `任务` 相同（避免 `inbox/ddaw/ddaw`）。
- **数据路径** 为容器/NAS 绝对路径，提交前须存在；也可在本页「上传入湖」走 ZIP 候选（与台账并行）。
- 飞书多维表格 **不再** 作为系统数据源（`FEISHU_BITABLE_SYNC_ENABLED=0`）；可选仅作人工备忘，见 [FEISHU_BITABLE_OPS.md](./FEISHU_BITABLE_OPS.md)。

## 6. 推荐数据闭环

### 现网（今日可执行）

```text
采集原图 → inbox(raw_pool) → 开启 Campaign → 标注/外协回传 → returned
  → 提交入库审核 → ingest → 数据目录 → 训练
```

验证：`python HSAP/as.py pending` 或 `GET /api/v1/pending`。

## 6.1 数据目录「范围」（二级下拉）

数据目录用 **视角 + 两级下拉**，勿与送标工作台 pending（始终按 **inbox 批次目录**）混淆：

| 视角 | 第一级 | 第二级 | 含义 |
|------|--------|--------|------|
| **训练包**（默认） | `dms_v1` 等 | `dam` / `addw_face` / `前向·粗检测` / `前向·细分类` … | 该包下各任务的 train/val 快照；前向在 registry 为单任务双 mode，目录按 mode 拆开显示 |
| **采集批次** | 任务（如 `dam`） | `0516 批次` 等 mode | 单波送标质量 |
| **车道线** | lane pack | — | Lane 列表统计 |

增量条（合并前）仍在磁盘 `packs/<pack>/<task>/sources/<批次名>/`；合并用 `python HSAP/as.py build dms dam --pack dms_v1 --all-sources`。

- 送标/审核：送标工作台或 **采集批次** 视角。
- 训练发版：**训练包 → 任务**；新版本在 `workflow.registry.yaml` 的 `active_packs` 启用。

### 目标态（DATA_LAKE）

上传 → staging → quality.json → 审核 → curated 版本 → 数据目录。见 [DATA_LAKE_CHECKLIST.md](./DATA_LAKE_CHECKLIST.md)、差距 [DATA_LAKE_GAP.md](./DATA_LAKE_GAP.md)。

## 7. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 待处理批次为 0 | inbox 无目录或无图 | 按 §3 落盘，或上传后 **送入 inbox** |
| 上传成功但批次仍空 | 未 promote | 等分析完成 → 点 **送入 inbox** |
| 画布无图 | inbox 路径空 | [QA_GAP_REPORT.md](./QA_GAP_REPORT.md) |
| DAM 无散点、ADDW 有 | 曾见 Docker 内 symlink 断链 | 已修复 `resolve_task_data_for_scan`；数据目录点 **刷新** |

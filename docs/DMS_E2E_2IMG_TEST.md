# DMS 2 图端到端测试手册（上下文备忘）

> 更新：2026-06-16  
> 用途：避免多轮对话丢失状态；记录 E2E 批次、脚本、已知问题与后续待测项。

---

## 1. 测试目标

验证 **QA 门禁完整链路**（DMS / ADDW）：

```text
raw_pool → 开 Campaign 标注 → 提交质检 → 质检通过 → 导出 YOLO → 提交 build → 审核批准 → ingested（进训练包）
```

与已完成的 **Unified Ingest SDK**、**ADAS MOON-3D** smoke 并列，本手册专指 **2 张图 DMS 小批次 E2E**。

---

## 2. 当前测试批次（已创建）

| 字段 | 值 |
|------|-----|
| project | `dms` |
| task | `addw`（ADDW 分心检测，4 类 bbox） |
| batch | `e2e_2img_20260616` |
| pack（入库目标） | `dms_v1`（`workflow.registry.yaml` active_packs） |
| campaign_id | `59f7c8fd8402c072bbbf` |
| cvat_task_id | `7` |
| cvat_job_id | `7` |
| cvat_job_url | `http://127.0.0.1:8080/tasks/7/jobs/7` |

### 数据路径

```text
HSAP/datasets/dms/inbox/addw/e2e_2img_20260616/
  images/train/
    eye_open__001_snap_dam_0416_cloudy_5_109.jpg
    eye_open__002_snap_dam_0522_smoke_phone_484.jpg
  labels/ls_annotations/          # CVAT 同步后写入
  labels/yolo/                      # 同步时顺带写（可选）
  batch.meta.yaml                   # stage 随流程推进更新
```

宿主机 inbox 目录为 **root 所有**（docker 创建）；标注/同步由 **hsap-platform 容器** 写入，属正常。

图片来源：从 `addw/20260525_pilot/images/train/` 复制前 2 张。

### 平台入口

- 标注画布：`http://127.0.0.1:8787/labeling/annotate/59f7c8fd8402c072bbbf`
- 标注进度：搜 `e2e_2img_20260616`
- 导出与入库：`/labeling/export`
- 审核队列：`/system/audit`

### 当前进度（2026-06-16 实测）

| 项 | 状态 |
|----|------|
| 落盘 2 图 | ✅ |
| register-batch raw_pool | ✅ |
| open Campaign | ✅ `out_for_labeling` |
| CVAT 标注 + 同步 | ✅ API：`saved=2, shapes=2`；`labeled=2/2` |
| 提交质检 | ✅ |
| 质检通过 | ✅ → `labeling_submitted` |
| 导出 YOLO | ✅ `written=2`（需 **重启 hsap-worker** 后 Job 才走新 runner） |
| build + ingested | ✅ `packs/dms_v1/addw/` 含 2 条 labels；`stage=ingested` |

**全流程结论**：数据已 merge 进 `datasets/dms/packs/dms_v1/addw/`（`labels/train` + `labels/val` 各 1 条）；`stage=ingested`。

---

## 3. 自动化脚本

### 3.1 Shell 入口

```bash
cd /home/chengfanglu/DATA/HSAP

# 查看状态
bash scripts/smoke_dms_e2e_2img.sh info
# 或
python3 platform/as_platform/tests/run_dms_e2e_pipeline.py info

# 标完后跑全流程（提交→质检→导出→build→校验 ingested）
bash scripts/smoke_dms_e2e_2img.sh run

# 等待标注（最多 600s）再跑
DMS_E2E_WAIT_LABEL_SEC=600 bash scripts/smoke_dms_e2e_2img.sh run-wait

# 重新 setup（会覆盖复制 2 图 + register + open campaign）
bash scripts/smoke_dms_e2e_2img.sh setup
```

### 3.2 Python 实现

`platform/as_platform/tests/run_dms_e2e_pipeline.py`

- `info` — 打印 campaign_id、stage、labeled 数
- `setup` — 调 API open campaign
- `run` — API 驱动：submit → review all good → export job → submit-build-batch → approve → 断言 `ingested` + pack sources

成功标志：stdout 末尾 `DMS_E2E_PIPELINE_OK`

### 3.3 环境变量

| 变量 | 默认 |
|------|------|
| `HSAP_API` | `http://127.0.0.1:8787` |
| `DMS_E2E_BATCH` | `e2e_2img_20260616` |
| `DMS_E2E_TASK` | `addw` |
| `DMS_E2E_PACK` | `dms_v1` |
| `DMS_E2E_MIN_IMAGES` | `2` |

---

## 4. 相关已完成工作（同会话 / 前序 commit）

### Commit `0b8ade0` — Unified Ingest SDK

- `platform/as_platform/data/promote/` — DMS/ADAS promote_batch
- ADAS cuboid export / fit / `adas_moon3d_v1`
- `platform/as_platform/tests/test_unified_ingest_sdk.py`（7 项单元测试）
- `scripts/smoke_adas_promote.sh`
- `scripts/smoke_labeling_api.sh` 已接入上述测试

### 离线测试（均已 PASS）

```bash
bash scripts/smoke_labeling_api.sh          # 含 API（platform :8787）
bash scripts/smoke_adas_promote.sh
python3 platform/as_platform/tests/test_unified_ingest_sdk.py
```

---

## 5. 已知问题与修复记录

### 5.1 「立即同步」点击无反馈（UI）

**现象**：用户点「立即同步」似乎没反应。

**根因（已确认）**：

1. **后端正常**：`POST /api/v1/labeling/cvat/sync/{campaign_id}` 返回 200，`saved=2, shapes=2`。
2. **前端 UX**：
   - 自动同步每 45s 跑时 `syncInFlight=true`，手动点击被 **静默丢弃**（无提示）。
   - `shapes=0` 时（CVAT 未 Ctrl+S 保存）仅更新顶栏灰色小字，**无 alert**，易被误认为无效。

**修复**（`AnnotationPage.tsx`，待 `build_web.sh` 后生效）：

- 同步进行中再点 → 顶栏提示「同步进行中，请稍候…」
- 手动同步结束 → **始终 alert**（含「暂无新标注，请先 CVAT 保存」说明）

**操作提示**：CVAT 画框后必须 **Ctrl+S 保存**，再点「立即同步」。

### 5.2 inbox 目录权限

`datasets/dms/inbox/addw/*` 由 docker 创建为 root；宿主机直接写 `labels/` 会 Permission denied。应通过平台 API/容器操作。

### 5.3 `register-batch` 计数

`images=4` 偶发（扫描逻辑）；实际仅 2 张 jpg，以 `progress total_tasks=2` 为准。

### 5.4 API `labeling/batches` limit

查询 `limit` 最大 **100**（非 200），E2E 脚本已修正。

### 5.5 `get_batch_export_stats` ORM

已在 session 外读 `camp.project` 修为先提取 `project`（commit `0b8ade0`）。

---

## 6. 平台复现步骤（协调员）

1. **送标工作台** → 待送标 → `e2e_2img_20260616` → 开始标注（若已开 Campaign 则跳过）
2. **标注画布** → CVAT 画框 → **Ctrl+S** → **立即同步**（或等 45s 自动同步）
3. **标注进度** → **提交质检**
4. **标注质检** → 逐张 Good（或跑脚本自动全 Good）
5. **导出与入库** → 待导出 → **执行导出** → 待 build → **提交 build**
6. **审核队列** → 批准 `build_dms`
7. **数据目录** → 训练包 `dms_v1` → `addw` → 见 `sources/e2e_2img_20260616`

---

### 5.10 质检详情看不到图 / 框（已修）

**原因 1（主因）**：`<img src="/api/.../review-image">` **不会带 Bearer Token** → 401，页面显示「图片加载失败」或空白。

**修复**：`QualityReviewPage` 改为 `fetchReviewImageBlob` + `URL.createObjectURL` 带鉴权加载。

**原因 2**：质检 overlay 只读 `labels/{stem}.txt`，CVAT 同步写在 `labels/yolo/`、`labels/ls_annotations/`。

**修复**：`review.py` 多路径解析 + 支持 ls_annotations JSON 画框。

**原因 3**：图片列表 `rglob *.jpg` 重复（大小写扩展名）→ 质检队列显示 4 张实为 2 张。

**修复**：改用 `_iter_batch_images` 去重。

**注意**：若 CVAT 框未保存或宽高为 0，底栏仍显示「标注: 无」——需画布内画有效框并 Ctrl+S。

---

`AS_JOB_EXECUTOR=worker`，Job 在 **hsap-worker** 进程执行。容器若长期未重启，可能仍跑旧版 `labeling_export`（误调 `as.py build`）。

```bash
docker restart hsap-worker hsap-platform
bash scripts/build_web.sh && docker restart hsap-platform   # UI 变更后
```

### 5.7 `build_dms` 校验过严（已修）

**原问题**：`validate_dms_task()` 要求整个 `packs/dms_v1/addw` 已存在（且常指向损坏的 workspace 软链）。

**修复**：`validate_dms_inbox_batch(batch_dir)` 只校验 inbox 批次已有 YOLO labels。

### 5.8 `dms_v1` 损坏软链（已修）

`datasets/dms/packs/dms_v1` 曾指向不存在的 `/data/workspace/DMS/DATASET/...`，`mkdir` 报 `File exists`。

**修复**：`pack_registry.resolve_pack_dir` / `DmsYoloPromoteAdapter` 检测断链并回退为 HSAP 内真实目录。

### 5.9 `refresh_yaml` 拖垮 build Job（已修）

**原问题**：`promote_inbox_batch` 内 `run_refresh(root)` 无 `--task`，因其他任务（如 ddaw）无 pack 目录而 exit 1，导致 Job 失败（数据其实已 promote）。

**修复**：`run_refresh(root, task=task)`；单批次 promote 只刷新对应任务 yaml。

### 分包给本人走「我的标注」（2026-06-16）

已用代码将 2 张均分给 **卢承方（user_id=5，飞书登录）**：

- `assigned=2`，`pending=2`，`completed=0`
- Campaign 已重置为 `in_progress` / `out_for_labeling`，原标注 JSON 已清空，可重新画框

**我的标注入口**：http://127.0.0.1:8787/labeling/my-tasks?campaign=59f7c8fd8402c072bbbf

若用 **dev 登录**（user_id=9 同名账号），需另分配或改用飞书账号登录。

```bash
# 再次分配（协调员 API）
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  http://127.0.0.1:8787/api/v1/labeling/campaigns/59f7c8fd8402c072bbbf/assign-tasks \
  -d '{"mode":"even","user_ids":[5]}'
```

---

- [x] 跑通 submit → 质检 → 导出 → build → `ingested`
- [ ] 前端 rebuild 后复测「立即同步」反馈（已改 `AnnotationPage.tsx`）
- [ ] UI 手工与脚本结果对照
- [ ] 将 `smoke_dms_e2e_2img.sh run` 接入 `smoke_labeling_api.sh`
- [ ] 提交上述 bugfix commit

---

## 8. 服务与端口

| 服务 | 地址 |
|------|------|
| HSAP 平台 | `http://127.0.0.1:8787` |
| CVAT（iframe） | `http://127.0.0.1:8080` |
| API 健康 | `GET /api/v1/health` |

```bash
docker compose up -d platform worker
docker compose -f docker-compose.yml -f docker-compose.cvat.yml up -d  # CVAT
bash scripts/build_web.sh && docker restart hsap-platform            # UI 更新后
```

---

## 9. 其他参考批次（非本 E2E）

| batch | campaign_id | 说明 |
|-------|-------------|------|
| `addw/20260525_pilot` | `149329641efe128c00f2` | 24 图，曾 in_review |
| ADAS `val_front6mm_pilot` | — | `smoke_adas_promote.sh` CLI 已 PASS |

ADAS registry 在 **HSAP 仓库外**：`data/送标/adas/adas.registry.yaml`。

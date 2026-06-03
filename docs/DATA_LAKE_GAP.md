# 数据入湖清单 vs HSAP 实现差距

对照 [DATA_LAKE_CHECKLIST.md](DATA_LAKE_CHECKLIST.md) 阶段 A～E 与当前 `as_platform` 能力。

| 阶段 | 清单要求 | HSAP 现状 | 差距 |
|------|----------|-----------|------|
| **A 上传接入** | zip/目录上传、进度、candidate_id | `POST /api/v1/data/upload/file`、`DatasetCandidate` 表；**analyzed 后可 `POST .../promote-inbox`** | 无统一 `lake/staging/` 路径约定；进度条依赖前端 upload |
| **A** | staging 区隔离 | 候选写入 DB + 磁盘路径 | 未强制 `lake/staging/<project>/<candidate_id>/` 目录规范 |
| **B 自动分析** | 上传后异步 quality worker | `inspect-upload`、部分 catalog 刷新 | 无独立 QualityWorker Job；DMS/Lane 报告未统一落 `quality.json` |
| **B** | DMS/Lane 指标 | Catalog、`catalogDms`、validate 脚本 | Catalog 已展示采样指标（条/饼/竖柱/雷达/划分柱/散点/密度）；**非**上传触发全自动 |
| **C 审核流** | 自动提交审核单 | `approvals`、`submit` API | 已有；与送标 register 联动 |
| **C** | 通过/驳回规范 | `approve`/`reject` | 已有 |
| **D 版本入湖** | 审核后晋级 curated | `ingest_incremental`、`register_batch` stage | **主路径在 ml.py/as.py**，非 candidate→lake 闸门 |
| **D** | catalog 索引更新 | `GET /catalog` refresh | 已有 |
| **E 运维安全** | 失败可读、重试 | Job 队列、approval 备注 | 部分；上传重试靠前端 |

## 已有可复用组件

- 数据候选：`platform/as_platform/db/models.py` → `DatasetCandidate`
- 上传 API：`server.py` → `upload/file`、`inspect-upload`
- 审核：`audit/queue.py`、`/api/v1/approvals/*`
- 入湖 CLI：`as.py build` / `add` + `ingest_incremental.py`

## 建议下一里程碑（未在本汇总 plan 全量实现）

1. 统一 staging 根目录与环境变量 `AS_LAKE_STAGING_ROOT`
2. 上传完成 → 入队 `quality_analyze` Job → 写 `quality.json`
3. 审核通过后调用现有 `ingest_incremental` 并更新 `batch.meta` stage

## 验收脚本

```bash
bash HSAP/scripts/smoke_manifest_alignment.sh
bash HSAP/scripts/smoke_platform_api.sh
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/v1/pending/gates
```

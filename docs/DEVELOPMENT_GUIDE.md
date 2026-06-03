# HSAP — Huaxu Sentinel Active Safety Platform

本文档说明 **HSAP** 仓库的开发约定、架构边界、关键设计决策，以及后续扩展原则。

---

## 1. 项目定位

**HSAP**（Huaxu Sentinel Active Safety Platform，华胥 Sentinel 主动安全平台）用于把数据、审核、训练、晋级流程平台化，覆盖：

- DMS（驾驶员监测）数据闭环
- Lane（车道线）数据闭环
- 后续 AEB 感知任务扩展

核心目标不是替代训练框架，而是把「协作流程」和「可追溯治理」做成平台能力。

---

## 2. 设计思想（为什么这样分层）

### 2.1 三层解耦（最重要）

顶层目录严格分离为：

- `platform/`：编排层（API、权限、审核、任务、Web）
- `algorithms/`：算法代码层（YOLO/UFLD 适配与注册）
- `datasets/`：数据层（数据包、inbox、sources）

这样做的价值：

- 平台升级不会污染算法代码
- 算法替换不会影响平台鉴权/审核
- 数据规范可以独立演进
- 便于把平台容器化、训练留宿主机或 GPU worker

### 2.2 平台只编排，不绑死训练实现

平台不直接实现训练算法，而是通过：

- `workflow.registry.yaml` 管理激活包和规则
- `algorithms/registry.yaml` 注册算法适配器
- `jobs/runner.py` 将动作路由到适配器/CLI

这保证了新增任务时只需加适配器与注册，不必改大量平台代码。

### 2.3 审核先行（治理优先于自动化）

所有写操作（build/train/promote/register 等）默认进审核队列，批准后再执行。  
原因：主动安全模型影响上线质量，必须可审计、可回放、可追责。

### 2.4 双执行模式（研发效率 + 平台治理）

- `thread`：API 进程内执行（单机调试）
- `worker`：API 入 Redis 队列，Worker 异步执行（推荐）

这样既支持单机快速迭代，也支持后续多机扩展。

---

## 3. 代码结构总览

```text
HSAP/
├── as.py                        # CLI 入口（add/build/train/eval/promote 等）
├── workflow.registry.yaml       # 流程与数据包策略
├── platform/
│   ├── as_platform/
│   │   ├── api/                 # FastAPI + auth routes
│   │   ├── auth/                # 飞书 OAuth、JWT、权限依赖
│   │   ├── db/                  # SQLAlchemy engine/models/init
│   │   ├── audit/               # 审核单服务
│   │   ├── jobs/                # 任务队列、执行与状态同步
│   │   ├── redis/               # Redis 事件与队列
│   │   ├── data/                # pending/catalog/organize/register
│   │   └── agents/              # tool/graph/trace
│   └── web/                     # React + Vite 前端
├── algorithms/                  # 算法注册与适配器
├── datasets/                    # 数据软链入口
├── scripts/                     # 启动、迁移、worker 等脚本
└── docs/                        # 文档（本文件）
```

---

## 4. 配置系统

### 4.1 业务配置：`workflow.registry.yaml`

该文件定义：

- 数据落盘路径模板（inbox/sources）
- `active_packs` 激活训练包
- 自动化策略（如评估门限）
- lane 合并列表路径与训练配置

### 4.2 运行配置：环境变量

关键变量：

- `AS_DB_*` / `AS_DATABASE_URL`：PostgreSQL
- `AS_REDIS_URL`：Redis 连接
- `AS_JOB_EXECUTOR=thread|worker`
- `FEISHU_APP_ID/FEISHU_APP_SECRET`
- `AS_JWT_SECRET`

默认开发环境从 `manifests/feishu.env` 读取。

---

## 5. 数据与权限模型

### 5.1 数据库（PostgreSQL）

核心表：

- `users`
- `roles`
- `permissions`
- `approvals`
- `jobs`
- 关系表：`user_roles`、`role_permissions`

遗留 `jsonl` 通过 `scripts/db_migrate_from_sqlite.py` 导入。

### 5.2 RBAC 角色

默认角色：

- `admin`：全权限 + 用户管理
- `reviewer`：审批权限
- `engineer`：提交训练/入库审核
- `labeler`：登记与有限提交
- `viewer`：只读

权限检查统一在 `auth/deps.py` 的依赖中完成。

### 5.3 飞书登录

流程：

1. `/api/v1/auth/feishu/authorize` 跳转飞书
2. callback 交换 token 与用户信息
3. upsert 用户并签发 JWT
4. 前端保存 token，后续所有 API 带 `Bearer`

### 5.4 飞书多维表格（内网出站）

- 操作：[FEISHU_BITABLE_OPS.md](./FEISHU_BITABLE_OPS.md)；开发：[FEISHU_INTEGRATION_DEV.md](./FEISHU_INTEGRATION_DEV.md)
- 配置：`manifests/feishu.env` 中 `FEISHU_BITABLE_APP_TOKEN`、`FEISHU_BITABLE_TABLE_ID`
- API：`GET/POST /api/v1/integrations/feishu/bitable/*`；`FEISHU_BITABLE_SYNC_ENABLED=1` 时后台轮询回写
- 验证：`bash scripts/feishu_bitable_verify.sh`

---

## 6. 审核与任务执行链路

标准写操作链路：

1. 前端提交动作（如 `train_dms`）
2. API 检查权限
3. 写入 `approvals`（`pending`）
4. reviewer 批准
5. 生成 `jobs` 记录
6. 按执行模式运行：
   - `thread`：本进程执行
   - `worker`：Redis 入队，worker 消费
7. 回写 job/approval 结果

设计要点：

- 审核状态和执行状态分开建模
- 审批记录保留原始参数
- 执行结果截断保存，避免字段无限膨胀

---

## 7. 前端设计原则

前端目标是运营与协作，不是训练控制台：

- 先看板（pending/audit/job）
- 再动作（提交审核）
- 强调角色驱动菜单与按钮显隐
- 所有写操作走同一审核接口，不绕后门

关键页面：

- 登录页（飞书/开发登录）
- 送标工作台（操作 SOP 见 [LABELING_SOP.md](./LABELING_SOP.md)）
- 数据目录
- 审核管理
- Job 监控
- 算法迭代与日志

---

## 8. Docker 开发环境设计

默认 `docker-compose.yml` 提供：

- `postgres`：结构化数据
- `redis`：队列与事件
- `platform`：API + build 后前端
- `worker`：任务执行器
- `web-dev`（profile）：Vite 热更新

推荐命令：

```bash
cd HSAP
bash scripts/dev_up.sh
make dev    # 可选，前端热更新
```

---

## 9. 扩展指南

### 9.1 新增算法任务（推荐步骤）

1. 在 `algorithms/` 新增适配器（统一输入输出）
2. 更新 `algorithms/registry.yaml`
3. 在 `jobs/runner.py` 增加动作映射
4. 在 `audit/queue.py` 注册动作标签与审批范围
5. 前端添加动作入口（可选）

### 9.2 新增权限

1. 在 `db/init_db.py` 增加权限码
2. 分配到角色
3. 在 API 依赖中加 `require_permission(...)`
4. 前端通过 `hasPermission` 做显隐

### 9.3 新增数据项目（非 DMS/Lane）

1. `workflow.registry.yaml` 添加 `projects.<name>`
2. `data/core.py` 扩展 catalog/pending 聚合
3. 适配对应算法层和动作

---

## 10. 开发约束与原则

- 平台层不直接耦合具体训练脚本路径（通过 registry/adapter 间接访问）
- 不在 API 路由里堆业务逻辑，尽量下沉到 service 模块
- 审核动作必须幂等、可回放
- 对外路径配置集中在 `config.py`，避免散落硬编码
- 优先保证可观测性（trace/job/approval 全链路）

---

## 11. 已知边界（当前版本）

- Worker 仍是单消费者模型，后续可扩展多 worker + claim 机制
- 暂未引入 Alembic，当前通过启动时 `create_all` + 迁移脚本
- 飞书 state 目前内存存储，单实例可用；多实例建议改 Redis

---

## 12. 未来演进建议（路线图）

1. 引入 Alembic 进行正式数据库迁移管理
2. 增加 worker 心跳与任务重试策略
3. 增加审计看板（谁在何时审批了什么）
4. 将 trace 接入外部可观测系统（如 ClickHouse/ELK）
5. 将训练执行器彻底远端化（平台无 GPU 依赖）

---

## 13. 快速自检清单

上线前最小检查：

- `GET /api/v1/health` 返回 `db_connected=true` 且 `redis_connected=true`
- 飞书登录可进入系统，角色权限生效
- 提交审核 -> 批准 -> job 执行链路可跑通
- `as.py pending` 与前端 pending 数据一致
- worker 异常时有失败状态与错误信息落库

---

## 14. 数据入湖与自动质检清单

上传压缩包/文件夹后的“自动分析 -> 审核 -> 版本入湖 -> 数据目录展示”执行标准，见：

- [`docs/DATA_LAKE_CHECKLIST.md`](./DATA_LAKE_CHECKLIST.md)

该清单覆盖：

- 分阶段执行项（上传接入、自动分析、审核流、版本入湖、运维与安全）
- DMS/Lane 的最小质检指标与可视化字段
- 数据目录的 `train/val/test` 展示规范
- 责任角色与验收标准


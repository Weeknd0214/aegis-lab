# MinIO 暂存区（联调搭建）

HSAP **尚未**实现 S3 API 自动拉取；先起 MinIO 用于：**上传试验 + 对象路径规范**。数据进标注仍须落到 `datasets/.../inbox`（Console 上传后 **同步到目录**，或等 Phase C S3 拉取）。

## 1. 启动（与 HSAP 同 compose）

```bash
cd /home/chengfanglu/DATA/HSAP
docker compose --profile minio up -d
```

| 服务 | 地址 | 默认账号 |
|------|------|----------|
| S3 API | http://127.0.0.1:9000 | 见 `manifests/minio.env.example` |
| Console | http://127.0.0.1:9001 | 同上 |

创建桶 `hsap-staging`（仅首次）：

```bash
docker compose --profile minio run --rm minio-init
```

## 2. 上传试数据

Console → 桶 **hsap-staging** → 建目录，例如：

```text
addw/20250526_SE882/images/train/*.jpg
```

与飞书表一致：**任务 addw**、**批次名 20250526_SE882**（无子模式）。  
**联调现成小样**：见 [PILOT_BATCH.md](./PILOT_BATCH.md)（`20260525_pilot`，12 张，已落 inbox + MinIO）。

## 3. 让 HSAP 能读到（当前必做）

平台容器**不能**直接填 `s3://...`，需同步到挂载目录。

**方式 A：宿主机同步到 HSAP datasets（推荐联调）**

```bash
# 安装 mc 或使用 compose 里的 mc 容器
docker run --rm --network host \
  -v /home/chengfanglu/DATA/HSAP/datasets:/datasets \
  minio/mc:latest sh -c '
  mc alias set local http://127.0.0.1:9000 minioadmin minioadmin_change_me
  mc mirror --overwrite local/hsap-staging/addw/20250526_SE882 /datasets/dms/inbox/addw/20250526_SE882
'
```

飞书 **数据路径**（若开 AUTO_INGEST）填容器内路径：

```text
/data/hsap/datasets/dms/inbox/addw/20250526_SE882
```

**方式 B：只测 MinIO，暂不联动 HSAP**

仅验证 Console 上传、桶结构；HSAP 仍用送标工作台 **上传入湖** 或手工 inbox。

## 4. 与飞书台账

| 飞书字段 | 现在 | MinIO 成熟后 |
|----------|------|----------------|
| 数据路径 | NAS / inbox 绝对路径 | 可改为 `s3://hsap-staging/addw/20250526_SE882/`（待开发） |
| 备注 | 可写「对象在 MinIO hsap-staging」 | |

## 5. 安全提醒

- 默认账号密码仅 **内网联调**，勿暴露到公网。  
- 生产请改 `MINIO_ROOT_PASSWORD`，并用独立 AK/SK。  

## 6. 停止

```bash
docker compose --profile minio down
# 数据在卷 hsap_minio_data 中保留
```

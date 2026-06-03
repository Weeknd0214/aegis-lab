# 联调小样：`20260525_pilot`（addw）

已在本机准备好 **12 张** ADDW 检测原图（来自 `reports/gt_gallery/addw`，每类 3 张），用于走通：**飞书台账 →（可选 MinIO）→ inbox → HSAP 落盘/送标**。

## 1. 数据位置

| 位置 | 路径 |
|------|------|
| 宿主机 inbox | `/home/chengfanglu/DATA/HSAP/datasets/dms/inbox/addw/20260525_pilot/` |
| 平台容器内（飞书 **数据路径** / AUTO_INGEST） | `/data/hsap/datasets/dms/inbox/addw/20260525_pilot` |
| MinIO 对象前缀 | `hsap-staging/addw/20260525_pilot/images/train/*.jpg` |

目录结构：

```text
20260525_pilot/
  images/train/
    face__*.jpg
    eye_open__*.jpg
    nod_eye__*.jpg
    nod_face__*.jpg
```

## 2. 飞书表填一行（复制对照）

| 列 | 填写值 |
|----|--------|
| 项目 | `dms` |
| 任务 | `addw` |
| 子模式 | **留空**（可无此列） |
| 批次名 | `20260525_pilot` |
| 来源类型 | `联调样例` |
| 车型或场景 | `pipeline_test` |
| 数据路径 | `/data/hsap/datasets/dms/inbox/addw/20260525_pilot` |
| 状态 | 先 `草稿` → 核对后改 **`待落盘`** |
| 预估张数 | `12` |
| 备注 | `联调小样；对象已同步 MinIO hsap-staging/addw/20260525_pilot` |

**不要**把批次名写成 `addw` 或 `dms_v2`。

## 3. 推荐走通顺序

### A. 已有磁盘数据（最快）

1. 飞书新建上表一行 → 状态 **待落盘**。  
2. HSAP：配置 `manifests/feishu.env` 后执行同步，或送标工作台 **扫描 inbox / 落盘**。  
3. 批次进入 **待送标** → 开 Campaign → 内标 2 人各领几张验证分包。  

### B. 顺带练 MinIO

1. Console 打开 http://127.0.0.1:9001 → 桶 `hsap-staging` → 确认已有 `addw/20260525_pilot/`。  
2. 若删了桶内数据，从 inbox 再 mirror 一次：

```bash
docker run --rm --network host \
  -v /home/chengfanglu/DATA/HSAP/datasets:/datasets \
  minio/mc:latest sh -c '
  mc alias set local http://127.0.0.1:9000 minioadmin minioadmin_change_me
  mc mirror --overwrite /datasets/dms/inbox/addw/20260525_pilot \
    local/hsap-staging/addw/20260525_pilot
'
```

3. 飞书 **数据路径** 仍填容器 inbox 路径（当前不支持仅填 `s3://`）。

## 4. 验收点

- [ ] 飞书同步后 **Inbox路径**、**HSAP链接** 有值  
- [ ] 送标工作台能看到 `addw / 20260525_pilot`，约 12 张待送标  
- [ ] 开启标注后 task 可打开画布  
- [ ] （可选）MinIO Console 中对象数与 inbox 一致  

## 5. 清理

```bash
# 仅删 inbox 样例（需 root/容器内）
docker exec hsap-platform rm -rf /data/hsap/datasets/dms/inbox/addw/20260525_pilot

# MinIO 前缀
docker run --rm --network host minio/mc:latest sh -c '
  mc alias set local http://127.0.0.1:9000 minioadmin minioadmin_change_me
  mc rm -r --force local/hsap-staging/addw/20260525_pilot
'
```

飞书行改 **驳回/作废** 或删除即可。

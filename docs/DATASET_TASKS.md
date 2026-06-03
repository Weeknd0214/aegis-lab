# HSAP 数据目录 · 任务划分

## 域（domain）

| domain | 含义 | 平台任务 ID |
|--------|------|-------------|
| **dms** | 舱内驾驶员监控（人脸/疲劳/分心/DAM） | `ddaw`, `addw`, `addw_face`, `dam`（含 0516/0417 两批次） |
| **forward** | 前向 ADAS · 交通标志 | `forward`（含检测 + 细分类两种子模式） |

数据目录页任务下拉按域分组显示；**forward** 选中后需再选 **子模式**：`detect`（粗检测 4 类）或 `classify`（细分类 ~92 类）。

## DAM 任务 `dam`（合并原 dam / dam_0417）

同一套 **15 类** 驾驶员监控检测（face、眼嘴、眼镜/烟/手机、driver 等），仅采集批次不同：

| 子模式 | 原目录 | 说明 |
|--------|--------|------|
| **batch_0516** | `dam/`（dam_0516） | 约 5k 图 |
| **batch_0417** | `dam_0417/` | 约 2.5k 图 |

训练 yaml：`dam__batch_0516.yaml`、`dam__batch_0417.yaml`。别名：`dam_0417` → `dam` + `batch_0417`。

```bash
python datasets/dms/scripts/migrate_dam_layout.py \
  --pack-dir /path/to/packs/dms_v1 --dms-root /path/to/datasets/dms
```

## 前向任务 `forward`（合并原 isa / isa_class）

| 子模式 | 原任务 ID | 目录（包内） | 说明 |
|--------|-----------|--------------|------|
| **detect** | `isa` | `forward/detect/` | YOLO 检测：indicative / prohibitory / warning / vehicle |
| **classify** | `isa_class` | `forward/classify/` | 文件夹分类，具体牌型 |

训练 yaml：`manifests/yaml_active/forward__detect.yaml`、`forward__classify.yaml`  
训练命令示例：

```bash
SUBMODE=detect ./scripts/train.sh forward full
SUBMODE=classify ./scripts/train.sh forward full
```

入库 inbox：

- `datasets/dms/inbox/forward/detect/<batch>`
- `datasets/dms/inbox/forward/classify/<batch>`

## 迁移旧目录

若数据仍在 `packs/dms_v1/isa` 与 `isa_class`：

```bash
python datasets/dms/scripts/migrate_forward_layout.py \
  --pack-dir /path/to/packs/dms_v1 \
  --dms-root /path/to/datasets/dms
```

默认创建符号链接，不搬动原数据。完成后执行 `refresh_yaml.py` 并在平台 **数据目录** 点刷新。

## 兼容别名

脚本与 API 仍接受旧 ID，会自动映射：

- `isa` → `forward` + `detect`
- `isa_class` → `forward` + `classify`

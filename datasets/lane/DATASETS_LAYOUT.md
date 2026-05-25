# 多包数据集目录规范（DATASET + DATASET-AddBy-*）

## 目录约定

```
lane0_copy/
├── DATASET/                              # 基线包 v1，冻结不覆盖
│   ├── images/ ...
│   ├── annotations/segmentation_masks/ ...
│   ├── list/train_gt.txt                 # 仅本包内相对路径: images/... mask/...
│   └── manifest.json
│
├── DATASET-AddBy-zhangsan-20260615/      # 工程师增量包（独立目录）
│   ├── images/ ...
│   ├── annotations/segmentation_masks/ ...
│   ├── list/train_gt.txt
│   └── manifest.json
│
├── lists_merged/                         # 跨包合并后的训练列表（不写回各包）
│   └── train_all_v2.txt                  # 行内带包名前缀，见下
│
└── datasets_registry.json                # 登记所有包与合并列表版本
```

**命名规则：** `DATASET-AddBy-<工程师姓名>-<日期>`  
- 日期建议 `YYYYMMDD`，例如 `20260615`  
- 姓名用英文/拼音，避免空格（可用 `_`）

## 列表文件格式（合并训练）

`data_root` 设为 **`lane0_copy`**（各包的父目录），合并列表每行两列，路径**带包名前缀**：

```
DATASET/images/src_.../frame_000001.jpg DATASET/annotations/segmentation_masks/src_.../frame_000001.png
DATASET-AddBy-zhangsan-20260615/images/src_.../frame_000001.jpg DATASET-AddBy-zhangsan-20260615/annotations/...
```

UFLD 配置示例（**推荐：在 config 里写 train_packs**）：

```python
# configs/mufld_lane_multi_pack.py
data_root = '/home/chengfanglu/DATA/lane0_copy'
train_packs = ['DATASET', 'DATASET-A']   # 短名可在 datasets_registry.json 的 aliases 里映射
pack_list_name = 'list/train_gt.txt'
merged_list_dir = 'lists_merged'
```

`python train.py configs/mufld_lane_multi_pack.py` 会自动合并并缓存到 `lists_merged/train__DATASET__....txt`。

别名示例 `datasets_registry.json`：

```json
"aliases": {
  "DATASET-A": "DATASET-AddBy-zhangsan-20260615"
}
```

## 工作流

### 1. 新建增量包（工程师提交 archive + train_val_gt.txt）

```bash
conda activate lane_light
python scripts/build_ufld_pack.py \
  --src /path/to/new_archive \
  --parent /home/chengfanglu/DATA/lane0_copy \
  --engineer zhangsan \
  --date 20260615
```

生成：`DATASET-AddBy-zhangsan-20260615/`

### 2. 合并多包训练列表（不改动 DATASET v1）

```bash
python scripts/merge_ufld_lists.py \
  --data-root /home/chengfanglu/DATA/lane0_copy \
  --out lists_merged/train_all_v2.txt \
  --prefix-from-pack \
  DATASET/list/train_gt.txt \
  DATASET-AddBy-zhangsan-20260615/list/train_gt.txt
```

### 3. 训练

```bash
cd /home/chengfanglu/DATA/BK2/UFLD
# configs 里 data_root=lane0_copy, train_list=lists_merged/train_all_v2.txt
python train.py configs/mufld_lane_culane.py
```

### 4. 登记版本

合并脚本加 `--update-registry` 会写入 `datasets_registry.json`。

## 原则

| 项 | 做法 |
|----|------|
| 基线复现 | 永远保留 `DATASET/list/train_gt.txt`，训练用副本 `lists_merged/*.txt` |
| 增量隔离 | 每个工程师一个 `DATASET-AddBy-*`，不往 DATASET 里混贴文件 |
| 磁盘 | 默认硬链接；跨盘用 `--copy` |
| 去重 | 合并时按**图像路径**去重，先出现的包优先（`--base` 指定主包） |

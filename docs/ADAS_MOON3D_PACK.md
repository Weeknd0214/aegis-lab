# ADAS MOON-3D 训练包 `adas_moon3d_v1`

## 目录结构

```text
datasets/adas/packs/adas_moon3d_v1/
├── sources/{batch}/
│   ├── images/
│   ├── calib/
│   └── labels/quaternion_json/
├── lists/
│   ├── train_stems.txt
│   └── val_stems.txt
└── manifests/
    └── pack_index.yaml
```

## class_id（BK2/MOON 顺序）

| ID | 类别 |
|----|------|
| 0 | pedestrian |
| 1 | car |
| 2 | truck |
| 3 | bus |
| 4 | motorcycle |
| 5 | tricycle |
| 6 | traffic cone |

定义于 [`data/送标/adas/adas.registry.yaml`](../../data/送标/adas/adas.registry.yaml) 与 [`datasets/labeling.registry.yaml`](../datasets/labeling.registry.yaml)。

## 管线

1. **labeling_export** — CVAT ls_annotations → `labels/quaternion_json/*.json`
2. **cuboid_fit_3d**（有 calib 时自动触发）— 补全 3D 字段
3. **build_adas**（审核）— `promote_batch` 复制到 pack + 刷新 stem 列表

## CLI

```bash
# 导出（平台 Job 或脚本）
PYTHONPATH=platform python3 -c "from as_platform.labeling.export_cuboid_batch import export_batch; ..."

# 3D 拟合
PYTHONPATH=platform python3 -c "from as_platform.labeling.fit_cuboid_batch import fit_batch; ..."

# 入包
python as.py build adas cuboid_7cls --batch val_front6mm_pilot --pack adas_moon3d_v1
```

## Smoke

```bash
bash scripts/smoke_adas_promote.sh
```

## 与 dms/packs/adas_v1 的区别

- `dms/packs/adas_v1`：2D YOLO 历史包（[`scripts/organize_adas.py`](../scripts/organize_adas.py)）
- `datasets/adas/packs/adas_moon3d_v1`：MOON-3D quaternion_json 3D GT

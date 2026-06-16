# 数据湖 inbox 示例根目录

本目录 **镜像** HSAP 真实数据湖路径，复制后可直接被「扫描数据湖」识别。

## ADAS 2D / 3D 都在 `adas/` 下

| 路径 | 类型 | project | task |
|------|------|---------|------|
| **`adas/inbox/det_7cls/`** | ADAS **2D** 七类 | `adas` | `det_7cls` |
| **`adas/inbox/cuboid_7cls/`** | ADAS **3D** MOON | `adas` | `cuboid_7cls` |

DMS 舱内数据仍在 `dms/inbox/`（addw、ddaw、dam 等），不含 ADAS 七类。

## 完整目录树

```text
datasets/
├── dms/inbox/                          project=dms
│   ├── addw/20260616_addw_pilot/
│   ├── ddaw/20260616_ddaw_pilot/
│   ├── addw_face/20260616_face_pilot/
│   ├── dam/batch_0516/20260616_dam_wave/
│   ├── forward/detect/20260616_fwd_det/
│   └── forward/classify/20260616_fwd_cls/
├── adas/inbox/                         project=adas
│   ├── det_7cls/20260616_adas2d_pilot/     ★ 2D 七类
│   └── cuboid_7cls/20260616_3d_pilot/      ★ 3D MOON
└── lane/inbox/20260616_lane_pilot/     project=lane
```

## 样例批次清单

见 [`manifest.yaml`](manifest.yaml)。

## 复制

```bash
bash ../copy_to_inbox.sh
```

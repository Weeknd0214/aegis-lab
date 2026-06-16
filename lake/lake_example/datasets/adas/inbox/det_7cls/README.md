# ADAS 2D 七类检测（YOLO）

```
adas/inbox/det_7cls/{批次名}/images/
```

## 台账 / API

| 字段 | 值 |
|------|-----|
| **project** | `adas` |
| **task** | `det_7cls` |

## 与 3D 同项目、不同任务

| | ADAS 2D（本目录） | ADAS 3D |
|---|-------------------|---------|
| 路径 | `adas/inbox/det_7cls/` | `adas/inbox/cuboid_7cls/` |
| task | `det_7cls` | `cuboid_7cls` |
| 标注 | 矩形框 bbox | cuboid 3D |
| 训练包 | adas_v1 | adas_moon3d_v1 |

## 样例

- `20260616_adas2d_pilot/`

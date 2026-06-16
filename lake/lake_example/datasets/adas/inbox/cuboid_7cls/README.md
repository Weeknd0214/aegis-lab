# ADAS 3D Cuboid 七类（MOON-3D）

```
adas/inbox/cuboid_7cls/{批次名}/
  images/
  calib/          ← 建议有，用于 3D 拟合
```

## 台账 / API

| 字段 | 值 |
|------|-----|
| **project** | `adas` |
| **task** | `cuboid_7cls` |

## 与 2D 的区别（同在 adas 项目下）

| | ADAS 2D | ADAS 3D（本目录） |
|---|---------|-------------------|
| 路径 | `adas/inbox/det_7cls/` | `adas/inbox/cuboid_7cls/` |
| task | `det_7cls` | `cuboid_7cls` |
| 标注 | 矩形框 bbox | cuboid 3D |
| 导出 | YOLO | quaternion_json |
| 训练包 | adas_v1 | adas_moon3d_v1 |

## 样例

- `20260616_3d_pilot/`

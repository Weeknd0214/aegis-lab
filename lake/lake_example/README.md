# 数据湖 inbox 落盘示例

本仓库镜像 HSAP 真实 inbox 路径。  
**详细树形说明见 [`datasets/README.md`](datasets/README.md)**，批次清单见 [`datasets/manifest.yaml`](datasets/manifest.yaml)。

## ADAS 2D / 3D（同在 adas 项目下）

| 类型 | 路径 | project | task |
|------|------|---------|------|
| **ADAS 2D 七类** | `datasets/adas/inbox/det_7cls/{批次}/` | `adas` | `det_7cls` |
| **ADAS 3D MOON** | `datasets/adas/inbox/cuboid_7cls/{批次}/` | `adas` | `cuboid_7cls` |

DMS 舱内（addw/ddaw/dam 等）仍在 `datasets/dms/inbox/`。

## 复制到数据湖

```bash
bash copy_to_inbox.sh
```

然后：**批次台账 → 扫描数据湖 → 登记到台账**。

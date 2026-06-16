类型: ADAS · 3D Cuboid 七类 (MOON-3D)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
★ 同属 project=adas；2D 在同级 det_7cls/ ★

API 登记:
  项目 (project): adas
  任务 (task):    cuboid_7cls
  子模式:         (空)

数据湖路径:
  datasets/adas/inbox/cuboid_7cls/{批次名}/
    images/
    calib/              ← 相机内参，建议必填

与 2D 的区别:
  - 3D 本目录 → task=cuboid_7cls, cuboid 标注, 训练包 adas_moon3d_v1
  - 2D 在 adas/inbox/det_7cls/ → task=det_7cls, 矩形框, 训练包 adas_v1

标完导出: labels/quaternion_json/*.json

复制示例:
  cp -a lake_example/datasets/adas/inbox/cuboid_7cls/20260616_3d_pilot \
      HSAP/datasets/adas/inbox/cuboid_7cls/

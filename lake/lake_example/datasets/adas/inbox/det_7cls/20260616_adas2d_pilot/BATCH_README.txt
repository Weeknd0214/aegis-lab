类型: ADAS · 2D 七类检测（YOLO）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
★ 与 3D 同属 project=adas，task 不同 ★

API 登记:
  项目 (project): adas
  任务 (task):    det_7cls
  子模式:         (空)

数据湖路径:
  datasets/adas/inbox/det_7cls/{批次名}/images/

与 3D 的区别:
  - 2D 本目录 → task=det_7cls, 矩形框标注, 训练包 adas_v1
  - 3D 在 adas/inbox/cuboid_7cls/ → task=cuboid_7cls, cuboid 标注, 训练包 adas_moon3d_v1

复制示例:
  cp -a lake_example/datasets/adas/inbox/det_7cls/20260616_adas2d_pilot \
      HSAP/datasets/adas/inbox/det_7cls/

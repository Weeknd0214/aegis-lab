# DMS 标注分期验收（addw pilot）

## P0：dam / ddaw（检测）

- [ ] 批次台账入湖 → inbox 有 `images/train`
- [ ] 送标工作台「待送标」可见批次
- [ ] 进入标注：左侧工具箱（face 等）+ 保存
- [ ] 提交后 `batch.meta` stage = `labeling_submitted`，「待入库」Tab 可见
- [ ] 导出 Job 成功后 stage = `returned`
- [ ] 提交入库审核 → build 通过

## P1：addw / addw_face（当前 pilot）

Pilot：`inbox/addw/20260525_pilot`（12 张）

- [x] `dms_detect.xml` 四类标签
- [x] `dms_pose.xml`：face 框 + 37 关键点（`kp_00`–`kp_36`）
- [x] `export_ls_to_yolo.py`：LS JSON → YOLO detect / YOLO pose
- [ ] 标注保存至 `labels/ls_annotations/*.json`
- [ ] 提交 / 导出 / 待入库全链路（见 P0 检查项）
- [ ] addw_face 导出 txt 每行 116 字段，通过 `validate_pose_label`

```bash
python3 datasets/dms/scripts/test_export_ls_to_yolo.py
```

## P2：forward / lane

- [ ] `forward__detect` / `forward__classify` registry 模板
- [ ] lane `lane_culane.xml` 画布 smoke

## 自动化

```bash
bash scripts/smoke_labeling_api.sh
bash scripts/smoke_pending_gate.sh
python3 scripts/lake_checklist_audit.py
```

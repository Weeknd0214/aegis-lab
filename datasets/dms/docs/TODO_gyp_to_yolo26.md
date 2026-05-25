# GYP 数据整理 → YOLO26 RKNN 迁移 Todo

> 数据根目录：`/home/chengfanglu/DATA/DMS/DATASET/gyp`（约 **45G**，已自 `gyp_org` / `BK2/archive/gyp` 迁入）  
> 配置：`/home/chengfanglu/DATA/DMS/DATASET/configs/`  
> 目标工程：`/home/chengfanglu/DATA/DMS/Code/yolo26_rknn_ultralytics-main`

---

## 阶段 0：环境与目录（先做）

- [ ] **0.1** 确认 conda：`clrnet_export` / 新建 `yolo26` 环境，能跑 `yolo train` / `yolo export format=rknn`
- [ ] **0.2** RKNN 量化环境单独建 venv（与 ultralytics 依赖隔离，见 README-EN）
- [ ] **0.3** 确定目标芯片平台（如 `rk3588`）写入后续 convert 命令
- [ ] **0.4** 统一数据根目录 `DMS/DATASET/dms_yolo/`（使用 `scripts/refresh_yaml.py`）
  ```
  dms_yolo/
  ├── yaml/          # 各任务 yaml，path 为相对路径
  ├── ddaw/ -> ../gyp/ddaw_1124
  ├── addw/, addw_face/, isa/, dam/, dam_0417/, isa_class/
  ├── manifests/
  └── README.md
  ```
  迁移服务器: `scripts/pack_dms_yolo.sh` 或 `rsync --copy-links`

---

## 阶段 1：盘点源数据（BK2/archive/gyp）

| 业务 | 源路径 | 格式 | 体量 | 类别数 |
|------|--------|------|------|--------|
| DDAW | `DATASET/gyp/ddaw_1124` | YOLO images/labels | ~646M | 9 |
| ADDW | `DATASET/gyp/addw_0523` | YOLO | ~553M | 4 |
| ADDW 人脸 | `DATASET/gyp/yoloface-0726` | YOLO pose | ~1.6G | face + 37 kpts |
| ISA | `DATASET/gyp/isa_detect` | YOLO | ~40G | 4 |
| ISA 分类 | `DATASET/gyp/isa_class_0116` | 文件夹分类 | ~448M | 多类 |
| DAM | `DATASET/gyp/dam_src_0417` / `dam_0516` | jpg+xml / YOLO | ~540M + ~930M | 待确认 |
| DOWN | `down/yolov5-6.2` | 代码+runs，数据在 yaml 指向服务器路径 | 待查本地 data |

- [ ] **1.1** 对每个子项目跑一遍统计：train/val 图片数、标签数、空标签、坏图
- [x] **1.2** 唯一数据根：`DMS/DATASET/gyp/`（已从 archive 补齐 isa / yoloface / isa_class）
- [x] **1.3** 已删除 `gyp_org` 及 `BK2/archive/gyp` 中重复数据目录（约释放 40G+）

---

## 阶段 2：转换为 Ultralytics/YOLO26 标准结构

### 划分原则（必守）

**不要按总量随机划分 train/val**，必须 **按类别分层**，使各类在 train/val 中的比例接近（默认 val≈10%）。

- **YOLO 检测**：`scripts/stratified_split.py yolo`  
  合并现有 train+val 为池子后，按「图像所含最稀有类」优先依次划分，避免稀有类全进 train。
- **文件夹分类**：`scripts/stratified_split.py classify`  
  **每个类别目录内独立**划分（与 `isa_preprocess.py` 思路一致），禁止全库 `random.sample`。
- 划分前用 `--dry-run` 查看各类 val 占比；满意后再去掉 `--dry-run` 执行。

```bash
cd DMS/DATASET/scripts
python stratified_split.py yolo --root ../gyp/ddaw_1124 --val-ratio 0.1 --dry-run
python stratified_split.py yolo --root ../gyp/ddaw_1124 --val-ratio 0.1 --seed 42
python stratified_split.py classify --root ../gyp/isa_class_0116 --src-split train --val-ratio 0.1 --dry-run
```

每个检测任务目标结构：

```
dms_yolo/<task>/
  images/train/
  images/val/
  labels/train/    # 与 images 同名 .txt
  labels/val/
  <task>.yaml
```

- [ ] **2.1 DDAW**（优先，与 DMS 疲劳最相关）
  - 源：`ddaw_1124`（已是 YOLO 布局）
  - 复制或软链到 `dms_yolo/ddaw/`
  - 编写 `ddaw.yaml`：`path`、`nc: 9`、`names`（与 `gyp_org/configs/ddaw.yaml` 一致）
  - 校验 train/val 一一配对

- [ ] **2.2 ADDW 检测**
  - 源：`addw_0523`
  - 同上，生成 `addw.yaml`（4 类）

- [ ] **2.3 ISA 检测**（体量大，可放后）
  - 源：`isa/jiancexunlian/isa_detect`（约 5 万 train 图）
  - 生成 `isa.yaml`（4 类：indicative / prohibitory / warning / vehicle）
  - **必须**用 `stratified_split.py yolo` 按类重划分（约 6 万图，先 `--dry-run`）

- [ ] **2.4 DAM**
  - 源：`dam/src_data_0417_pick`（jpg + xml）
  - [ ] 编写 xml → YOLO txt 转换脚本（可参考原 yolov5 `dam-0516` 流程）
  - [ ] 划分 train/val 后写入 `dms_yolo/dam/`

- [ ] **2.5 ADDW 人脸 Pose**（若上 RKNN）
  - 源：`yoloface-0726`
  - 确认 yolo26 是否支持 `format=rknn` + pose；若不支持，单独保留 ultralytics820 链路
  - 生成 `yoloface.yaml`（`kpt_shape: [37,3]`）

- [ ] **2.6 DOWN / 其他**
  - 清点 `down/` 下是否有本地 `images/labels`；若仅 yaml 指远程路径，从 archive 或备份补数据

---

## 阶段 3：清单与量化校准集（RKNN 必需）

`rknn_export/convert.py` 需要 **图片路径列表 txt**（默认 `coco_subset_20.txt`）。

- [ ] **3.1** 每个任务生成 `manifests/<task>_calib_20.txt`（20～50 张代表性图，覆盖场景）
- [ ] **3.2** 每个任务生成 `manifests/<task>_train.txt` / `val.txt`（可选，用于训练记录）
- [ ] **3.3** 图片尺寸统一策略：
  - 检测默认 **640×640**（与 `yolo export format=rknn` 一致）
  - 记录原图分辨率，训练 yaml 里可设 `imgsz`

---

## 阶段 4：迁入 yolo26 工程并训练

路径：`DMS/Code/yolo26_rknn_ultralytics-main`

- [ ] **4.1** 在工程下建 `data/` 或软链：`data/dms_yolo -> ../../DATASET/dms_yolo`
- [ ] **4.2** 冒烟训练（每个任务先 1 epoch / 小 subset）：
  ```bash
  yolo detect train data=../../DATASET/dms_yolo/ddaw/ddaw.yaml model=yolo26n.pt epochs=1 imgsz=640
  ```
- [ ] **4.3** 正式训练记录：`runs/`、best.pt、指标
- [ ] **4.4** 导出 RKNN 用 ONNX：
  ```bash
  yolo export model=runs/detect/train/weights/best.pt format=rknn imgsz=640
  ```

---

## 阶段 5：ONNX → RKNN

- [ ] **5.1** 使用任务专属校准列表：
  ```bash
  python rknn_export/convert.py \
    --model-path <best.onnx> \
    --platform rk3588 \
    --data-path ../../DATASET/dms_yolo/manifests/ddaw_calib_20.txt
  ```
- [ ] **5.2** 板端验证：原始输出 6 tensor + CPU 后处理（decode/NMS，见 README-EN）
- [ ] **5.3** 与旧 yolov5/yolov8 模型对比精度与延迟

---

## 阶段 6：清理与文档

- [ ] **6.1** 确认 `BK2/archive/gyp` 无再用压缩包（**已完成删 16 个，约释 43G**）
- [ ] **6.2** 更新 `gyp_org/README.md`：指向 `dms_yolo` 新路径
- [ ] **6.3** 在 `DMS/Code/yolo26_rknn_ultralytics-main` 增加 `docs/DMS_DATASETS.md`（类名、路径、训练命令）

---

## 建议优先级

1. **DDAW** → 冒烟训练 → RKNN 导出（验证整条链路）
2. **ADDW 检测** → 同上
3. **DAM**（需 xml 转换）
4. **ISA**（40G，训练成本高，按需）
5. **人脸 Pose**（依赖 RKNN 对 pose 的支持情况）

---

## 当前磁盘参考

| 路径 | 大小（删包后） |
|------|----------------|
| `BK2/archive/gyp` | **~51G** |
| `DMS/DATASET/gyp_org` | ~48G（若与 archive 重复，合并后可再省） |
| 系统盘可用 | **~137G** |

---

*生成日期：2026-05-20*

# MonoFlex — Flexible Monocular 3D Object Detection (CVPR 2021)

上游论文实现，已 vendored 到 `code/`。

## 环境

```bash
conda create -n monoflex python=3.8
conda activate monoflex
pip install torch torchvision  # 建议 CUDA 11.x
pip install -r code/requirements.txt
cd code/model/backbone/DCNv2 && bash make.sh
cd ../../.. && pip install -e code/
```

## 数据

修改 `code/config/paths_catalog.py` 指向 KITTI 或自有 3D 检测数据。

与 aegis-lab 标注导出（`cuboid_7cls` → quaternion JSON）的对接见 `docs/CVAT_INTEGRATION.md` 与 `algorithms/adas_mono3d/`。

## 训练（经 adapter）

```python
from algorithms.monoflex.adapter import train_local
train_local(batch_size=8)
```

或直接：

```bash
cd algorithms/monoflex/code
CUDA_VISIBLE_DEVICES=0 python tools/plain_train_net.py \
  --batch_size 8 --config runs/monoflex.yaml --output output/exp
```

## 同步源码

从 workspace 更新：

```bash
bash scripts/vendor_monoflex.sh
```

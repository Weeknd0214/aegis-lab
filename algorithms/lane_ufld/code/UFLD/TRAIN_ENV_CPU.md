## lane_light + CPU PyTorch（UFLD 训练）

### 1. 激活环境

```bash
source /home/chengfanglu/miniconda3/etc/profile.d/conda.sh
conda activate lane_light
```

### 2. 已安装依赖（`lane_light`）

- `torch` / `torchvision`（**CPU 轮子**，来自 `https://download.pytorch.org/whl/cpu`）
- `opencv-python`, `tqdm`, `tensorboard`, `addict`, `scikit-learn`, `pathspec`（与 `requirements.txt` 对齐；`sklearn` 包名在 pip 中为 `scikit-learn`）

自检：

```bash
python -c "import torch; print('torch', torch.__version__, 'cuda=', torch.cuda.is_available())"
```

### 3. 数据与配置

- 默认数据根仍指向 `lane0_reorganized/lane_training_pack`（见 `configs/mufld_lane_culane.py`）。
- **CPU 建议**使用 `configs/mufld_lane_culane_cpu.py`（`batch_size=4`，学习率与 warmup 已按 batch 相对 16 做了粗略缩放）。内存不够可改配置或命令行覆盖：

```bash
cd /home/chengfanglu/DATA/BK2/UFLD
python train.py configs/mufld_lane_culane_cpu.py --batch_size 2
```

### 4. 运行训练

```bash
cd /home/chengfanglu/DATA/BK2/UFLD
python train.py configs/mufld_lane_culane_cpu.py
```

说明：

- `train.py` 已改为在 **无 CUDA** 时使用 `cpu`；原仓库中写死的 `CUDA_VISIBLE_DEVICES=1,2` 与 `.cuda()` 已去掉，避免 CPU 机直接报错。
- 首次 `pretrained=True` 会下载 ResNet 骨干权重，需联网。
- CPU 训练很慢，建议先用小 `epoch` / 小 `batch_size` 做通路测试。

### 5. 可选：DataLoader `num_workers`

当前 `data/dataloader.py` 里 `num_workers=8`。若 CPU 内存紧张或不想多进程读盘，可自行把该值改小（例如 `0` 或 `2`）。

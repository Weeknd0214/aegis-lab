# CPU 单机训练示例：batch 需显著减小；学习率可按 batch 相对 16 做线性缩放（可选）。
#
# layout 同 configs/mufld_lane_culane.py；
# lane_light 环境与安装说明见 TRAIN_ENV_CPU.md

dataset = "CULane"
data_root = "/home/chengfanglu/DATA/lane0_copy/DATASET"

epoch = 50
batch_size = 4
optimizer = "SGD"
# 若在 CPU 上不收敛可先试更小 lr，例如 batch=4 时约 0.1 * (4 / 16) = 0.025
learning_rate = 0.025
weight_decay = 1e-4
momentum = 0.9

scheduler = "multi"
steps = [25, 38]
gamma = 0.1
warmup = "linear"
# warmup 与原配置按 batch 比例对齐（原为 695 @ bs=16）
warmup_iters = 174

use_aux = True
griding_num = 200
backbone = "18"

sim_loss_w = 0.0
shp_loss_w = 0.0

note = "lane_training_pack_cpu_bs4"
log_path = None

finetune = None
resume = None

test_model = "./model/culane_18.pth"
test_work_dir = "./tmp"

num_lanes = 4

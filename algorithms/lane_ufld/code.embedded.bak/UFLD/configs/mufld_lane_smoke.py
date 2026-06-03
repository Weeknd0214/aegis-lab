# Smoke test: few samples, 1 epoch, small batch (CPU or GPU).
dataset = "CULane"
data_root = "/home/chengfanglu/DATA/lane0_copy/DATASET"
train_list = "list/train_gt_smoke.txt"

epoch = 1
batch_size = 2
optimizer = "SGD"
learning_rate = 0.025
weight_decay = 1e-4
momentum = 0.9

scheduler = "multi"
steps = [1]
gamma = 0.1
warmup = "linear"
warmup_iters = 10

use_aux = True
griding_num = 200
backbone = "18"

sim_loss_w = 0.0
shp_loss_w = 0.0

note = "dataset_smoke_test"
log_path = "./log"

finetune = None
resume = None

test_model = "./model/culane_18.pth"
test_work_dir = "./tmp"

num_lanes = 4

# MUFLD lane pack in CULane-style layout for UFLD training.
# Data root layout:
#   <data_root>/images/...
#   <data_root>/annotations/segmentation_masks/...
#   <data_root>/list/train_gt.txt   (two columns: training split only)
#   <data_root>/list/val_gt.txt     (validation pairs, optional custom loop)
#   <data_root>/list/test.txt       (held-out test images, one per line)

dataset = 'CULane'
data_root = '/home/chengfanglu/DATA/lane0_copy/DATASET'

epoch = 50
batch_size = 16
optimizer = 'SGD'
learning_rate = 0.1
weight_decay = 1e-4
momentum = 0.9

scheduler = 'multi'
steps = [25, 38]
gamma = 0.1
warmup = 'linear'
warmup_iters = 695

use_aux = True
griding_num = 200
backbone = '18'

sim_loss_w = 0.0
shp_loss_w = 0.0

note = 'lane_training_pack_v1'
log_path = './log'

finetune = None
resume = None

test_model = './model/culane_18.pth'
test_work_dir = './tmp'

num_lanes = 4

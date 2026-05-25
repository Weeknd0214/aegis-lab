# DATA
dataset = 'Tusimple'
# data_root = 'C:\\data\\Tusimple\\test_set'
# data_root = 'C:\\data\\anno\\324lane'
# data_root = 'C:\\data\\Tusimple\\train_set'
data_root = '/data/panh28/yk_syj/data/train_0306'
# TRAIN
epoch = 600
batch_size = 64
optimizer = 'Adam'    #['SGD','Adam']
# learning_rate = 0.1
learning_rate = 1e-5
weight_decay = 1e-4
momentum = 0.9

scheduler = 'cos'     #['multi', 'cos']
# steps = [50,75]
gamma = 0.1
warmup = 'linear'
warmup_iters = 100

# NETWORK
backbone = '34'
griding_num = 100
use_aux = False

# LOSS
sim_loss_w = 1.0
shp_loss_w = 0.0

# EXP
note = 'lane_res34_2ch_syj_0906_minilearn'

log_path = './log'

# FINETUNE or RESUME MODEL PATH
finetune = None
resume = "/data/panh28/yk_syj/code/UFLD/log/20230906_161808_lr_1e-04_b_64lane_res34_2ch_syj_0906/ep068.pth"
# TESTNone
test_model = './model/lane_m599_all.pth'
# test_model = './model/tusimple_18.pth'
test_work_dir = './tmp'

num_lanes = 2

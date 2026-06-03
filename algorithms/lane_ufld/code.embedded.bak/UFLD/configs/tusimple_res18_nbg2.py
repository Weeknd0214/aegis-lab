# DATA
dataset = 'Tusimple'
data_root = '/mnt/HDisk2T/liuxy51/ganxian/train_2024_03_06_1'

# TRAIN
epoch = 500 # 10
batch_size =  32 # 4
optimizer = 'Adam'    #['SGD','Adam']
learning_rate = 1e-5
weight_decay = 1e-4
momentum = 0.9
scheduler = 'cos'     #['multi', 'cos']

# steps = [50,75]
gamma = 0.1
warmup = 'linear'
warmup_iters = 100

# NETWORK
backbone = '18'
griding_num = 100
use_aux = False

# LOSS
sim_loss_w = 1.0
shp_loss_w = 0.0

# EXP
note = '_ufld_2lanes_res18'

log_path = './log'

# FINETUNE or RESUME MODEL PATH
finetune = None
resume = None

# TESTNone
test_model = './model/lane_m599_all.pth'
test_work_dir = './tmp'

num_lanes = 2

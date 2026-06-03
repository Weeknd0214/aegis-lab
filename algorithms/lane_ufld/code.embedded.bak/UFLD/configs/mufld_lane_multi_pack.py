# Multi-pack training — control merged packs in this config.
# data_root = parent of DATASET / DATASET-AddBy-* / DATASET-A (alias).

from pathlib import Path

dataset = 'CULane'
data_root = str(Path(__file__).resolve().parents[5] / "datasets" / "lane")

# Pack names: directory under data_root, or alias from datasets_registry.json
train_packs = [
    'lane_v1',
]

# Default list inside each pack (relative to pack root)
pack_list_name = 'list/train_gt.txt'

# Cached merged list (auto filename from pack names if merged_train_list is None)
merged_list_dir = 'lists_merged'
merged_train_list = None   # e.g. 'lists_merged/train_all_v2.txt'
remerge_train_list = False # True to rebuild merged list every run

# Single-pack fallback (ignored when train_packs is set)
train_list = 'list/train_gt.txt'

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

note = 'multi_pack_v2'
log_path = './log'

finetune = None
resume = None

test_model = './model/culane_18.pth'
test_work_dir = './tmp'

num_lanes = 4

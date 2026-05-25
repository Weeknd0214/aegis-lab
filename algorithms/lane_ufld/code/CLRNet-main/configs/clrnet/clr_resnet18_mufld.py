# CLRNet on lane0_copy MUFLD packs (1280x720)
# data_root = parent of DATASET / DATASET-AddBy-*

net = dict(type='Detector', )

backbone = dict(
    type='ResNetWrapper',
    resnet='resnet18',
    pretrained=True,
    replace_stride_with_dilation=[False, False, False],
    out_conv=False,
)

num_points = 72
max_lanes = 4
sample_y = range(710, 150, -10)

heads = dict(type='CLRHead',
             num_priors=192,
             refine_layers=3,
             fc_hidden_dim=64,
             sample_points=36)

iou_loss_weight = 2.
cls_loss_weight = 6.
xyt_loss_weight = 0.5
seg_loss_weight = 1.0

work_dirs = "work_dirs/clr/mufld_r18"

neck = dict(type='FPN',
            in_channels=[128, 256, 512],
            out_channels=64,
            num_outs=3,
            attention=False)

test_parameters = dict(conf_threshold=0.40, nms_thres=50, nms_topk=max_lanes)

epochs = 15
batch_size = 16

optimizer = dict(type='AdamW', lr=1.0e-3)
# ~144k / 16 * 15 — adjust after changing train_packs
total_iter = (144117 // batch_size + 1) * epochs
scheduler = dict(type='CosineAnnealingLR', T_max=total_iter)

eval_ep = 3
save_ep = 5

img_norm = dict(mean=[103.939, 116.779, 123.68], std=[1., 1., 1.])
ori_img_w = 1280
ori_img_h = 720
img_w = 800
img_h = 320
cut_height = 160

train_process = [
    dict(
        type='GenerateLaneLine',
        transforms=[
            dict(name='Resize',
                 parameters=dict(size=dict(height=img_h, width=img_w)),
                 p=1.0),
            dict(name='HorizontalFlip', parameters=dict(p=1.0), p=0.5),
            dict(name='Affine',
                 parameters=dict(translate_percent=dict(x=(-0.1, 0.1),
                                                        y=(-0.1, 0.1)),
                                 rotate=(-10, 10),
                                 scale=(0.8, 1.2)),
                 p=0.7),
            dict(name='Resize',
                 parameters=dict(size=dict(height=img_h, width=img_w)),
                 p=1.0),
        ],
    ),
    dict(type='ToTensor', keys=['img', 'lane_line', 'seg']),
]

val_process = [
    dict(type='GenerateLaneLine',
         transforms=[
             dict(name='Resize',
                  parameters=dict(size=dict(height=img_h, width=img_w)),
                  p=1.0),
         ],
         training=False),
    dict(type='ToTensor', keys=['img']),
]

# --- MUFLD multi-pack (same as UFLD) ---
dataset_path = '/home/chengfanglu/DATA/lane0_copy'
train_packs = ['DATASET']
# train_packs = ['DATASET', 'DATASET-A']  # alias in datasets_registry.json
val_packs = ['DATASET']
pack_list_name = 'list/train_gt.txt'
pack_val_list_name = 'list/val_gt.txt'
merged_list_dir = 'lists_merged'
remerge_lists = False
write_lines_cache = True
lines_cache_dir = 'cache/mufld_lines'

dataset_type = 'MufldLane'
dataset = dict(
    train=dict(
        type=dataset_type,
        data_root=dataset_path,
        split='train',
    ),
    val=dict(
        type=dataset_type,
        data_root=dataset_path,
        split='val',
    ),
    test=dict(
        type=dataset_type,
        data_root=dataset_path,
        split='test',
        list_file='DATASET/list/test_gt.txt',
    ),
)

workers = 8
log_interval = 500
num_classes = max_lanes + 1
ignore_label = 255
bg_weight = 0.4
lr_update_by_epoch = False

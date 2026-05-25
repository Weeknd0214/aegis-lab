# Smoke: copy fields from clr_resnet18_mufld.py and override below
# (CLRNet Config does not use _base_ inheritance)

net = dict(type='Detector', )
backbone = dict(type='ResNetWrapper', resnet='resnet18', pretrained=True,
                replace_stride_with_dilation=[False, False, False], out_conv=False)
num_points = 72
max_lanes = 4
sample_y = range(710, 150, -10)
heads = dict(type='CLRHead', num_priors=192, refine_layers=3, fc_hidden_dim=64, sample_points=36)
iou_loss_weight = 2.
cls_loss_weight = 6.
xyt_loss_weight = 0.5
seg_loss_weight = 1.0
work_dirs = "work_dirs/clr/mufld_r18_smoke"
neck = dict(type='FPN', in_channels=[128, 256, 512], out_channels=64, num_outs=3, attention=False)
test_parameters = dict(conf_threshold=0.40, nms_thres=50, nms_topk=max_lanes)
epochs = 1
batch_size = 4
optimizer = dict(type='AdamW', lr=1.0e-3)
total_iter = 32
scheduler = dict(type='CosineAnnealingLR', T_max=total_iter)
eval_ep = 1
save_ep = 1
img_norm = dict(mean=[103.939, 116.779, 123.68], std=[1., 1., 1.])
ori_img_w = 1280
ori_img_h = 720
img_w = 800
img_h = 320
cut_height = 160
train_process = [
    dict(type='GenerateLaneLine',
         transforms=[dict(name='Resize', parameters=dict(size=dict(height=img_h, width=img_w)), p=1.0)],
         training=True),
    dict(type='ToTensor', keys=['img', 'lane_line', 'seg']),
]
val_process = [
    dict(type='GenerateLaneLine',
         transforms=[dict(name='Resize', parameters=dict(size=dict(height=img_h, width=img_w)), p=1.0)],
         training=False),
    dict(type='ToTensor', keys=['img']),
]
dataset_path = '/home/chengfanglu/DATA/lane0_copy'
train_list_file = 'DATASET/list/train_gt_smoke.txt'
val_list_file = 'DATASET/list/train_gt_smoke.txt'
write_lines_cache = True
lines_cache_dir = 'cache/mufld_lines'
dataset_type = 'MufldLane'
dataset = dict(
    train=dict(type=dataset_type, data_root=dataset_path, split='train'),
    val=dict(type=dataset_type, data_root=dataset_path, split='val'),
    test=dict(type=dataset_type, data_root=dataset_path, split='test',
              list_file='DATASET/list/train_gt_smoke.txt'),
)
workers = 2
log_interval = 8
num_classes = max_lanes + 1
ignore_label = 255
bg_weight = 0.4
lr_update_by_epoch = False

CLRNet 使用说明（lane0_copy 数据）

代码目录：/home/chengfanglu/DATA/BK2/CLRNet-main
数据目录：/home/chengfanglu/DATA/lane0_copy/（与 UFLD 相同多包布局）

上游论文原版说明见同目录 README.md。


一、环境安装

source ~/miniconda3/etc/profile.d/conda.sh
cd /home/chengfanglu/DATA/BK2/CLRNet-main
bash scripts/setup_clrnet_env.sh
conda activate clrnet_lane

说明：
环境名默认 clrnet_lane
需要 NVIDIA GPU（main.py 使用 .cuda()）
安装包含 PyTorch、mmcv-full、python setup.py develop（编译 NMS）


二、数据目录

lane0_copy/
  DATASET/（images、annotations/segmentation_masks、list/）
  DATASET-AddBy-zhangsan-20260615/（增量包）
  lists_merged/（合并列表）
  datasets_registry.json（别名）

重要：dataset_path 填父目录 lane0_copy，不要只填 DATASET。

数据集类：clrnet/datasets/mufld.py（MufldLane），从 mask 提取车道折线。
目录规范：/home/chengfanglu/DATA/lane0_copy/DATASETS_LAYOUT.md


三、配置文件

configs/clrnet/clr_resnet18_mufld.py — 推荐，1280x720，多包
configs/clrnet/clr_resnet18_mufld_smoke.py — 冒烟

请改 configs/clrnet/clr_resnet18_mufld.py：

dataset_path = '/home/chengfanglu/DATA/lane0_copy'
train_packs = ['DATASET']
（多包：train_packs = ['DATASET', 'DATASET-A']，别名见 datasets_registry.json）
val_packs = ['DATASET']
pack_list_name = 'list/train_gt.txt'
remerge_lists = False

合并列表输出：lane0_copy/lists_merged/train__DATASET__....txt

图像与网络参数：
原图 1280x720
cut_height 160
网络输入 800x320
max_lanes 4


四、训练

conda activate clrnet_lane
cd /home/chengfanglu/DATA/BK2/CLRNet-main

首次冒烟前先建短列表：
head -64 /home/chengfanglu/DATA/lane0_copy/DATASET/list/train_gt.txt > /home/chengfanglu/DATA/lane0_copy/DATASET/list/train_gt_smoke.txt

冒烟：
python main.py configs/clrnet/clr_resnet18_mufld_smoke.py --gpus 0

正式：
python main.py configs/clrnet/clr_resnet18_mufld.py --gpus 0

权重目录：work_dirs/clr/mufld_r18/（由 config 里 work_dirs 决定）
多卡示例：--gpus 0 1

常用修改：
batch_size = 16
epochs = 15
optimizer = dict(type='AdamW', lr=1.0e-3)
换 train_packs 后请改 total_iter = (144117 // batch_size + 1) * epochs


五、预生成车道线缓存（推荐）

首轮会从 mask 现场提线，较慢。可先执行：

python tools/generate_mufld_lines.py --data-root /home/chengfanglu/DATA/lane0_copy --list DATASET/list/train_gt.txt

缓存目录：lane0_copy/cache/mufld_lines/


六、测试与推理

python main.py configs/clrnet/clr_resnet18_mufld.py --gpus 0 --test --load_from work_dirs/clr/mufld_r18/ckpt/best.pth

（--load_from 按实际 ckpt 路径填写）

说明：
没有 CULane 官方评测
预测会写成 lines.txt，日志 metric 为占位值


七、增量数据

1）建包（与 UFLD 共用脚本）：
python /home/chengfanglu/DATA/lane0_copy/scripts/build_ufld_pack.py --src /path/to/archive --parent /home/chengfanglu/DATA/lane0_copy --engineer zhangsan --date 20260615

2）config 增加包名：
train_packs = ['DATASET', 'DATASET-AddBy-zhangsan-20260615']
remerge_lists = True

3）重新训练：
python main.py configs/clrnet/clr_resnet18_mufld.py --gpus 0


八、路径速查

代码：/home/chengfanglu/DATA/BK2/CLRNet-main
数据父目录：/home/chengfanglu/DATA/lane0_copy
训练配置：configs/clrnet/clr_resnet18_mufld.py
数据集实现：clrnet/datasets/mufld.py
安装脚本：scripts/setup_clrnet_env.sh

UFLD 使用说明（lane0_copy 数据）

代码目录：/home/chengfanglu/DATA/BK2/UFLD
数据目录：/home/chengfanglu/DATA/lane0_copy/


一、环境

source ~/miniconda3/etc/profile.d/conda.sh
conda activate lane_light
cd /home/chengfanglu/DATA/BK2/UFLD


二、数据目录

lane0_copy/
  DATASET/（基线包，勿改 list/train_gt.txt）
    images/
    annotations/segmentation_masks/
    list/train_gt.txt（训练：图 + mask 两列）
    list/val_gt.txt
    list/test_gt.txt
    list/test.txt（仅图片）
  DATASET-AddBy-zhangsan-20260615/（增量包，结构同上）
  lists_merged/（多包合并列表，训练时自动生成）
  datasets_registry.json（短名别名）

增量包命名：DATASET-AddBy-姓名-YYYYMMDD（日期 8 位，如 20260615）
目录规范详见：/home/chengfanglu/DATA/lane0_copy/DATASETS_LAYOUT.md

新建增量包命令：

python /home/chengfanglu/DATA/lane0_copy/scripts/build_ufld_pack.py --src /path/to/archive --parent /home/chengfanglu/DATA/lane0_copy --engineer zhangsan --date 20260615

别名（config 里可写 DATASET-A）：编辑 lane0_copy/datasets_registry.json，例如：
{"aliases": {"DATASET-A": "DATASET-AddBy-zhangsan-20260615"}}


三、配置文件

configs/mufld_lane_multi_pack.py — 推荐，多包训练，用 train_packs 控制合并
configs/mufld_lane_culane.py — 单包，data_root 指向 DATASET 目录本身
configs/mufld_lane_smoke.py — 冒烟（少量样本）
configs/tusimple_res18_4lane_v1.py — 对接旧权重 best.pth（griding_num=100）

多包训练请改 configs/mufld_lane_multi_pack.py：

data_root = '/home/chengfanglu/DATA/lane0_copy'
train_packs = ['DATASET']
（多包示例：train_packs = ['DATASET', 'DATASET-A']）
pack_list_name = 'list/train_gt.txt'
remerge_train_list = False（增删包后改为 True，强制重建 lists_merged）

训练时自动合并列表到：lane0_copy/lists_merged/train__DATASET__....txt


四、训练

conda activate lane_light
cd /home/chengfanglu/DATA/BK2/UFLD

冒烟：
UFLD_NUM_WORKERS=0 python train.py configs/mufld_lane_smoke.py

正式（多包）：
python train.py configs/mufld_lane_multi_pack.py

断点续训：
python train.py configs/mufld_lane_multi_pack.py --resume log/你的实验目录/best.pth

日志与权重在：log/时间_lr_.../best.pth
无 GPU 时可设 UFLD_NUM_WORKERS=0

常用 config 项：
batch_size = 16
learning_rate = 0.1
use_aux = True（False 与旧 best.pth 一致，更省显存）
griding_num = 200（旧权重用 100）
num_lanes = 4


五、推理与测试

【5.1 可视化 demo】

先准备 test3.txt（示例取 3 张）：
awk '{print $1}' /home/chengfanglu/DATA/lane0_copy/DATASET/list/test_gt.txt | head -3 > /home/chengfanglu/DATA/lane0_copy/DATASET/test3.txt

python demo.py configs/tusimple_res18_4lane_v1.py --test_model log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.pth --data_root /home/chengfanglu/DATA/lane0_copy/DATASET

【5.2 批量测试】

python test.py configs/tusimple_res18_4lane_v1.py --test_model log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.pth --data_root /home/chengfanglu/DATA/lane0_copy/DATASET --test_list list/test_gt.txt

多包时 data_root 用 lane0_copy，例如：
python test.py configs/mufld_lane_multi_pack.py --test_model log/xxx/best.pth --data_root /home/chengfanglu/DATA/lane0_copy --test_list lists_merged/train__DATASET.txt

无 test_label.json 时只出预测，不算 TuSimple 官方指标。

【5.3 预测画到图上】

python vis_tusimple_pred.py --pred tmp/tusimple_eval_tmp.0.txt --data_root /home/chengfanglu/DATA/lane0_copy/DATASET --out_dir tmp/vis_pred


六、导出 ONNX

python pth_to_onnx.py --model_path log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.pth --output log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.onnx

需与训练时 backbone、griding_num、num_lanes 一致。


【6.1 VoVNet backbone】

已从 `BK2/archive/vovnet-detectron2-master` 移植 OSA+eSE 结构（无 detectron2 依赖），与 ResNet 相同接口。

| config `backbone` | 说明 |
|-------------------|------|
| `vov19slim` | V-19-slim-eSE，约 52.7M 参数（288×800） |
| `vov19slim_dw` | slim + depthwise |
| `vov19` / `vov39` / `vov57` / `vov99` | 更大变体 |

示例配置：`configs/tusimple_vov19slim_4lane_v1.py`

```bash
python train.py configs/tusimple_vov19slim_4lane_v1.py
python profile_model.py --backbone vov19slim --griding_num 100 --num_lanes 4
```

VoVNet **无** torchvision 预训练权重，需从头训或自行转换 detectron2 权重。旧 ResNet 的 `best.pth` **不能**直接用于 VoVNet。


七、路径速查

代码：/home/chengfanglu/DATA/BK2/UFLD
数据父目录：/home/chengfanglu/DATA/lane0_copy
基线数据：/home/chengfanglu/DATA/lane0_copy/DATASET
多包配置：configs/mufld_lane_multi_pack.py
已有权重：log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.pth

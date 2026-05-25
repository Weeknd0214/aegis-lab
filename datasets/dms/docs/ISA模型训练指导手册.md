1,链接webserver 
地址：192.168.1.175
密码：123
用户名：xzl

2,remmina 远程传数据

/home/xzl/yolov5-6.2 训练代码
/mnt/sas/xzl13/datasets/isa_detect  检测数据集
/home/xzl/datasets 分类数据集（最新的是 isa_class_1120）


3,vscode 

/home/xzl/yolov5-6.2 训练工程代码文件夹
 激活训练环境
conda activate /mnt/sas/xzl13/conda/yolov5s62

3.1 检测模型
3.1.1 数据处理
标注后的图片和xml标注文件整理到一个文件夹src_data下面。
所有.jpg图片放到src_data/images,所有xml文件放到src_data/labels
tar cvf isa_detect_1120.tar.gz src_data
/mnt/sas/xzl13/datasets 下新建文件夹 isa_detect_1120
remmina传输文件到下面
解压 
cd /mnt/sas/xzl13/datasets/isa_detect_1120
tar xvf isa_detect_1120.tar.gz 

执行脚本处理数据
python  isa_detect_preprocess.py  --src-data ./isa_detect_1124_test/src_data

拷贝检测数据到 /mnt/sas/xzl13/datasets/isa_detect
cd /mnt/sas/xzl13/datasets/isa_detect_1120
cp -r dst_data/* ../isa_detect/

3.1.2 服务器训练检测模型
检测训练脚本位置：/home/xzl/yolov5-6.2/train.py 
cd /home/xzl/yolov5-6.2/
nohup  python train.py --data isa-detect.yaml --weights '' --cfg yolov5s_isa.yaml --img 640 --batch-size 128 --device 1,2 > train_isa_detect_1124_log &

only modify train_isa_detect_1120_log for log

3.1.3 导出模型为onnx 
训练完模型保存位置/home/xzl/yolov5-6.2/runs/train/exp6/weights/best.pt
执行导出转换脚本
cd /home/xzl/yolov5-6.2/
python export.py --weights runs/train/exp6/weights/best.pt --include onnx
导出文件位置：/home/xzl/yolov5-6.2/runs/train/exp6/weights/best.onnx




3.2 分类模型

3.2.1 从检测数据集roi截图
cd /mnt/sas/xzl13/datasets/
python isa_roi_img.py --train-label  ./isa_detect_1120/dst_data/labels/train --val-label ./isa_detect_1120/dst_data/labels/val --save-dir ./isa_detect_1120/roi
roi截图后保存在/mnt/sas/xzl13/datasets/isa_detect_1120/roi下面。下载到本地，用于下一步分类处理数据

3.2.2 数据处理
从webserver下载上次训练数据集src_data到本地
将欧洲回传的截图或检测数据集roi截图拷贝到src_data相应文件夹下

在webserser的/home/xzl/datasets/ 下新建文件夹 isa_class_1120 ，并将本地处理完的src_data数据上传到此目录下。

分类数据处理脚本:
cd home/xzl/datasets/
python isa_preprocess.py --src-data ./isa_class_1120/src_data
cp /home/xzl/datasets/isa_class_1120/dst_data/* /home/xzl/datasets/isa_class_1120 

3.2.3 训练
/home/xzl/yolov5-6.2/classify/train.py 分类训练脚本
nohup python classify/train.py --model mobilenet_v3_large --data isa_class_1120 --epochs 80 --img 224 --device 3 > train_isa_clas_1120_log &

--data isa_class_1120 指定数据集到/home/xzl/datasets/isa_class_1120


训练完，生成文件在/home/xzl/yolov5-6.2/runs/train-cls/exp5下面。
模型文件在 /home/xzl/yolov5-6.2/runs/train-cls/exp5/weights/best.pt 

3.2.4 导出onnx模型
cd /home/xzl/yolov5-6.2
python export.py --weights runs/train-cls/isa1120_classify_mobilenetv3_large/weights/best.pt --include onnx --imgsz 224

--weights 指定新生成的模型文件
转生成onnx模型，
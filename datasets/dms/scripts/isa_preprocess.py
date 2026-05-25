import os
import random
import glob


import argparse
from pathlib import Path
import shutil
import sys
from PIL import Image
import cv2
import csv
from itertools import islice

FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]  # YOLOv5 root directory
print("-------------------ROOT=",ROOT)

# test_rate=0.05

# src_data_path = "./isa_class/src_data"

def process_img(src_data_path, test_rate):
        

    dst_data_path = src_data_path.replace('src_data','dst_data')
    # if not os.path.exists(dst_data_path):
    #     print("create dst_data = ", dst_data_path)
    #     os.mkdir(dst_data_path)

    list = glob.glob(os.path.join(src_data_path,"*/*.jpg"))
    print("len list = ",len(list))
    test_cout = int(test_rate*len(list))
    print("test_cout = ",test_cout)
    test_list=random.sample(list, test_cout)
    print("test_list len = ",len(test_list))

    # print("test_list  = ",test_list)

    dst_train_path=os.path.join(dst_data_path,'train')
    dst_test_path=os.path.join(dst_data_path,'test')
    print("dst_train_path={} , dst_test_path={}".format(dst_train_path,dst_test_path))
    if not os.path.exists(dst_train_path):
        os.makedirs(dst_train_path)
    if not os.path.exists(dst_test_path):
        os.makedirs(dst_test_path)

    class_name_list = []
    for x in  glob.glob(os.path.join(src_data_path, '*')):
        class_name_list.append(os.path.split(x)[-1])
    print("class_name_list = ",class_name_list)

    data_set_type = ['train','test']
    for class_name in class_name_list:
        for set in data_set_type:
            dst_class_dir = os.path.join(dst_data_path,set,class_name)
            if not os.path.exists(dst_class_dir):
                os.makedirs(dst_class_dir)
                print("create dst_class_dir = ",dst_class_dir)

    for class_name in class_name_list:
        sub_src_path = os.path.join(src_data_path, class_name)
        img_list = glob.glob(os.path.join(sub_src_path,'*.jpg'))
        total_len = len(img_list)
        test_cout = int(test_rate*len(img_list))
        if test_cout < 1:
            test_cout = 1
        print("test_cout = ",test_cout)
        print("class_name = ",class_name)
        test_list=random.sample(img_list, test_cout)
        print("test_list len = ",len(test_list))
        for src_img in img_list:
            img_name = os.path.split(src_img)[-1]
            # for date_set in data_set_type:
            dst_train_img_path=os.path.join(dst_train_path, class_name, img_name)
            dst_test_img_path=os.path.join(dst_test_path, class_name, img_name)
            # if src_img in test_list:
                
            # else:
            # dst_img_path=os.path.join(dst_train_path, class_name, img_name)
            
            print("src_img={},dst_train_img_path={},dst__test_img_path={}".format(src_img, dst_train_img_path, dst_test_img_path))
            if src_img in test_list:
                shutil.copy(src_img, dst_test_img_path)
                if total_len < 2:
                    shutil.copy(src_img, dst_train_img_path)  
            else:
                shutil.copy(src_img, dst_train_img_path)                  


def parse_opt():
    parser=argparse.ArgumentParser()

    parser.add_argument('--src-data',type=str,default=ROOT / "src_data",help='src dir')
    parser.add_argument('--test-rate',type=float,default=0.1,help='test_rate')
    # parser.add_argument('--src-test',type=str,default=ROOT / "src_test",help='src dir')
    parser.add_argument('--dst-data',type=str,default=ROOT / "dst_data",help='dst dir')
    # parser.add_argument('--prefix',type=str,default="dst",help='prefix name ')
    opt=parser.parse_args()

    print("src_data=%s" % (opt.src_data))
    print("test_rate=%s" % (opt.test_rate))
    # print("src_test=%s" % (opt.src_test))   
    print("dst_data=%s" % (opt.dst_data))
    # print("prefix=%s" % (opt.prefix))
    
    return opt

# python isa_preprocess.py --src-data ./isa_class_tsrd_gtsrb_eureg_cctsdb_tt100k/src_data 
# python isa_preprocess.py --src-data ./isa_class_tsrd_gtsrb_eureg_cctsdb_tt100k_speed/src_data 
# python isa_preprocess.py --src-data ./isa_class_1020/src_data
# python isa_preprocess.py --src-data ./isa_class_1023/src_data
# python isa_preprocess.py --src-data ./isa_class_1025/src_data
# python isa_preprocess.py --src-data ./isa_class_1026/src_data
# python isa_preprocess.py --src-data ./isa_class_1102/src_data
# python isa_preprocess.py --src-data ./isa_class_1120/src_data
# python isa_preprocess.py --src-data ./isa_class_1212/src_data
# python isa_preprocess.py --src-data ./isa_class_1221/src_data
# python isa_preprocess.py --src-data ./isa_class_1222/src_data
# python isa_preprocess.py --src-data ./isa_class_1224/src_data
# python isa_preprocess.py --src-data ./isa_class_1229/src_data
# python isa_preprocess.py --src-data ./isa_class_0103/src_data
# python isa_preprocess.py --src-data ./isa_class_0104/src_data
# python isa_preprocess.py --src-data ./isa_class_0108/src_data
# python isa_preprocess.py --src-data ./isa_class_0112/src_data
# python isa_preprocess.py --src-data ./isa_class_0116/src_data
def main(opt):

    if opt.src_data  and opt.dst_data:
        # train_ppm_to_jpg(opt.src_train, opt.dst_data)
        process_img(opt.src_data, opt.test_rate)
    

    

if __name__ == "__main__":
    opt = parse_opt()
    main(opt)
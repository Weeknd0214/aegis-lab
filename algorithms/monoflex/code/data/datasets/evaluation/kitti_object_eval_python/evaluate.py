import os
import time
import pdb
import fire
import math
import numpy as np
from . import kitti_common as kitti
from config.defaults import _C as cfg
import csv

def _read_imageset_file(path):
    with open(path, 'r') as f:
        lines = f.readlines()
    return [line.rstrip() for line in lines]

def evaluate(label_path,
             result_path,
             label_split_file,
             current_class=0,
             coco=False,
             score_thresh=-1,
             metric='R40'):
    
    from .eval import get_coco_eval_result, get_official_eval_result
    
    dt_annos = kitti.get_label_annos(result_path)
    if score_thresh > 0:
        dt_annos = kitti.filter_annos_low_score(dt_annos, score_thresh)
    val_image_ids = _read_imageset_file(label_split_file)
    gt_annos = kitti.get_label_annos(label_path, val_image_ids)
    if coco:
        return get_coco_eval_result(gt_annos, dt_annos, current_class)
    else:
        return get_official_eval_result(gt_annos, dt_annos, current_class, metric=metric)

def recover_obj_ori_ry_from_fixed_focal(ry, focal_factor):
    rot_y = np.array([
        [math.cos(ry),0,math.sin(ry)],
        [0,1,0],
        [-math.sin(ry),0,math.cos(ry)]
    ])

    point_start = np.matmul(rot_y, np.array([0.0, 0.0, 0.0]))
    point_end = np.matmul(rot_y, np.array([10.0, 0.0, 0.0]))
    rotation_y = -math.atan2((point_end[2] - point_start[2]) * focal_factor, point_end[0] - point_start[0])
    return rotation_y

def recover_obj_dims_from_fixed_focal(h, w, l, ori_ry, ry, focal_factor):
    ori_h = h

    ry_tmp = ori_ry + math.pi / 2
    rot_y = np.array([
        [math.cos(ry_tmp),0,math.sin(ry_tmp)],
        [0,1,0],
        [-math.sin(ry_tmp),0,math.cos(ry_tmp)]
    ])
    point_start = np.matmul(rot_y, np.array([0.0, 0.0, 0.0]))
    point_end = np.matmul(rot_y, np.array([10.0, 0.0, 0.0]))
    rotation_y_w = -math.atan2((point_end[2] - point_start[2]) / focal_factor, point_end[0] - point_start[0])
    ori_w = math.sqrt(math.pow(w * math.sin(rotation_y_w) * focal_factor, 2) + math.pow(w * math.cos(rotation_y_w), 2))

    ori_l = math.sqrt(math.pow(l * math.sin(ry) * focal_factor, 2) + math.pow(l * math.cos(ry), 2))

    return ori_h, ori_w, ori_l

def generate_kitti_3d_detection(prediction, predict_txt, img_x_scale, img_y_scale, focal_factor, classes=None):
    with open(predict_txt, 'w', newline='') as f:
        writer = csv.writer(f, delimiter=' ', lineterminator='\n')
        for p in prediction:
            p = p.numpy()
            p = p.round(4)
            type = classes[int(p[0])]
            p1x_list = p[1:].tolist()
            h = p1x_list[5]
            w = p1x_list[6]
            l = p1x_list[7]
            # ori_ry = recover_obj_ori_ry_from_fixed_focal(p1x_list[11], focal_factor)
            ry = p1x_list[11]
            row = [type, -1, -1] + [p1x_list[1] / img_x_scale] + [p1x_list[2] / img_y_scale] + [p1x_list[3] / img_x_scale] + [p1x_list[4] / img_y_scale] + [h, w, l] + [0, 0, 0, 0, 0, 0] + p1x_list[8:10] + [p1x_list[10] * focal_factor] + [0, ry, 0] + [p1x_list[12]]
            writer.writerow(row)

if __name__ == '__main__':
    fire.Fire()
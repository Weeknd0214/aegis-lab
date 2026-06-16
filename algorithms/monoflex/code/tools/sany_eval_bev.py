import datetime
import os
import logging
import math
import numpy as np
import copy
from data.datasets.kitti_utils import compute_obj_rotation_y_from_camera_euler_angle
from tools.sany_eval_utils import evaluate, eval_visual

ranges_GTs = [
    [-40.0, 80.0, -6.0, 6.0],  # car,
    [-40.0, 80.0, -6.0, 6.0],  # truck,
    [-40.0, 60.0, -6.0, 6.0],  # ped,
    [-40.0, 60.0, -6.0, 6.0],  # cyclist,
    [-40.0, 60.0, -6.0, 6.0],  # tricyclist,
    [-40.0, 80.0, -6.0, 6.0],  # largeV,
    [-40.0, 80.0, -6.0, 6.0],  # smallV,
    [-40.0, 40.0, -6.0, 6.0],  # trafficcone,
    [-40.0, 40.0, -6.0, 6.0],  # fence,
    [-40.0, 80.0, -6.0, 6.0],  # truckhead,
    [-40.0, 80.0, -6.0, 6.0],  # trucktail,
]

thr_center_dist_bev = [
    2.0,  # thr_iou_car,
    4.0,  # thr_iou_truck,
    2.0,  # thr_iou_ped,
    2.0,  # thr_iou_cyclist,
    2.0,  # thr_iou_tricyclist,
    4.0,  # thr_iou_largeV,
    2.0,  # thr_iou_smallV,
    2.0,  # thr_iou_trafficcone,
    2.0,  # thr_iou_fence,
    2.0,  # truckhead,
    4.0,  # trucktail,
]

thr_ious_bev = [
    0.001,  # thr_iou_car,
    0.001,  # thr_iou_truck,
    0.001,  # thr_iou_ped,
    0.001,  # thr_iou_cyclist,
    0.001,  # thr_iou_tricyclist,
    0.001,  # thr_iou_largeV,
    0.001,  # thr_iou_smallV,
    0.001,  # thr_iou_trafficcone,
    0.001,  # thr_iou_fence,
    0.001,  # truckhead,
    0.001,  # trucktail,
]

thr_ious_2D = [
    0.1,  # thr_iou_car,
    0.1,  # thr_iou_truck,
    0.01,  # thr_iou_ped,
    0.1,  # thr_iou_cyclist,
    0.1,  # thr_iou_tricyclist,
    0.1,  # thr_iou_largeV,
    0.1,  # thr_iou_smallV,
    0.01,  # thr_iou_trafficcone,
    0.1,  # thr_iou_fence,
    0.1,  # thr_iou_truckhead,
    0.1,  # thr_iou_truckhead,
]

display_min_num = 30

pre_range_extend_z = 2
pre_range_extend_x = 1

# label_line_field_index
label_fields = [
    "type",
    "truncated",
    "occluded",
    "2d_left",
    "2d_top",
    "2d_right",
    "2d_bottom",
    "3d_height",
    "3d_width",
    "3d_length",
    "lidar_loc_x",
    "lidar_loc_y",
    "lidar_loc_z",
    "lidar_euler_x",
    "lidar_euler_y",
    "lidar_euler_z",
    "cam_loc_x",
    "cam_loc_y",
    "cam_loc_z",
    "cam_euler_x",
    "cam_euler_y",
    "cam_euler_z",
]

truncated_ind = label_fields.index("truncated")
occluded_ind = label_fields.index("occluded")
box_left_ind = label_fields.index("2d_left")
box_top_ind = label_fields.index("2d_top")
box_right_ind = label_fields.index("2d_right")
box_bottom_ind = label_fields.index("2d_bottom")
cam_x_ind = label_fields.index("cam_loc_x")
cam_z_ind = label_fields.index("cam_loc_z")
length_ind = label_fields.index("3d_length")
height_ind = label_fields.index("3d_height")
width_ind = label_fields.index("3d_width")
cam_elx_ind = label_fields.index("cam_euler_x")
cam_ely_ind = label_fields.index("cam_euler_y")
cam_elz_ind = label_fields.index("cam_euler_z")


def get_bev_box(line):
    new_box = []
    cam_x = float(line[cam_x_ind])
    cam_z = float(line[cam_z_ind])
    length = abs(float(line[length_ind]))
    height = abs(float(line[height_ind]))
    width = abs(float(line[width_ind]))
    ry = compute_obj_rotation_y_from_camera_euler_angle(
        float(line[cam_elx_ind]), float(line[cam_ely_ind]), float(line[cam_elz_ind])
    )
    angle = np.rad2deg(ry)
    new_box.append(cam_z)
    new_box.append(cam_x)
    new_box.append(length)
    new_box.append(width)
    new_box.append(angle)
    new_box.append(height)

    return new_box


def get_2D_box(line):
    new_box = []
    left = float(line[box_left_ind])
    top = float(line[box_top_ind])
    right = float(line[box_right_ind])
    bottom = float(line[box_bottom_ind])

    new_box.append((left + right) / 2.0)
    new_box.append((top + bottom) / 2.0)
    new_box.append(right - left)
    new_box.append(bottom - top)
    new_box.append(0.0)

    return new_box


def compute_match_num(
    current_class,
    single_gt_list,
    single_pre_list,
    match_class_num,
    match_class_num_bev,
    is_type_strict,
    matched_gt_objs_lt=None,
    matched_pre_objs_lt=None,
):
    single_pre_list_temp = copy.deepcopy(single_pre_list)
    for gt_line in single_gt_list:
        match_2D_flag = False
        match_bev_flag = False
        name = gt_line[0]
        cls_ind = current_class.index(name)
        pre_index = 0
        for (
            pre_line
        ) in single_pre_list_temp:  # 一个pre匹配两个gt？？？？？？pre匹配上后需要减掉一个pre，那gt匹配上后是否也要减掉gt？
            if is_type_strict and name != pre_line[0]:  # 按类别计算匹配
                continue
            gt_box_bev = get_bev_box(gt_line)
            pre_box_bev = get_bev_box(pre_line)
            iou_score_bev = evaluate(gt_box_bev, pre_box_bev)  # 两者在BEV上进行iou计算
            gt_box_2D = get_2D_box(gt_line)
            pre_box_2D = get_2D_box(pre_line)
            iou_score_2D = evaluate(gt_box_2D, pre_box_2D)  # 两者在2D图上进行iou计算
            if iou_score_bev >= thr_ious_bev[cls_ind]:
                match_bev_flag = True
            if (
                iou_score_bev >= thr_ious_bev[cls_ind]
                or iou_score_2D >= thr_ious_2D[cls_ind]
            ):
                match_2D_flag = True
                break
            pre_index += 1
        if match_2D_flag:
            single_pre_list_temp.pop(pre_index)
            match_class_num[cls_ind] += 1
        if match_bev_flag:
            if is_type_strict:
                matched_gt_objs_lt[cls_ind].append(gt_box_bev)
                matched_pre_objs_lt[cls_ind].append(pre_box_bev)
            match_class_num_bev[cls_ind] += 1
    return


def compute_match_num2(
    current_class,
    single_gt_list,
    single_pre_list,
    match_class_num,
    match_class_num_bev,
    is_type_strict,
    matched_gt_objs_lt=None,
    matched_pre_objs_lt=None,
):
    gt_len = len(single_gt_list)
    pre_len = len(single_pre_list)
    score_np = np.zeros((gt_len, pre_len, 3), dtype=float)
    score_np[:, :, 0] = 1000.0

    for i, gt_line in enumerate(single_gt_list):
        name = gt_line[0]
        cls_ind = current_class.index(name)
        for j, pre_line in enumerate(single_pre_list):
            if is_type_strict and name != pre_line[0]:  # 按类别计算匹配
                continue
            gt_box_bev = get_bev_box(gt_line)
            pre_box_bev = get_bev_box(pre_line)
            center_dist = np.linalg.norm(
                np.array(
                    (gt_box_bev[0] - pre_box_bev[0], gt_box_bev[1] - pre_box_bev[1])
                )
            )
            iou_score_bev = evaluate(gt_box_bev, pre_box_bev)  # 两者在BEV上进行iou计算
            gt_box_2D = get_2D_box(gt_line)
            pre_box_2D = get_2D_box(pre_line)
            iou_score_2D = evaluate(gt_box_2D, pre_box_2D)  # 两者在2D图上进行iou计算
            score_np[i, j] = (center_dist, iou_score_bev, iou_score_2D)

    match_list = []
    match_i = set()
    match_j = set()

    match_way = 0
    sorted_inds = np.argsort(score_np.reshape(-1, 3)[:, match_way])
    for ind in sorted_inds:
        i = ind // pre_len
        j = ind % pre_len
        name = single_gt_list[i][0]
        cls_ind = current_class.index(name)
        if (
            (score_np[i, j, match_way] < thr_center_dist_bev[cls_ind])
            and (i not in match_i)
            and (j not in match_j)
        ):
            match_list.append((i, j))
            match_i.add(i)
            match_j.add(j)
            if is_type_strict:
                gt_box_bev = get_bev_box(single_gt_list[i])
                pre_box_bev = get_bev_box(single_pre_list[j])
                matched_gt_objs_lt[cls_ind].append(gt_box_bev)
                matched_pre_objs_lt[cls_ind].append(pre_box_bev)
            match_class_num_bev[cls_ind] += 1
            # match_class_num[cls_ind] += 1

    # match_way = 1
    # sorted_inds = np.argsort(score_np.reshape(-1, 3)[:, match_way])[::-1]
    # for ind in sorted_inds:
    #     i = ind // pre_len
    #     j = ind % pre_len
    #     name = single_gt_list[i][0]
    #     cls_ind = current_class.index(name)
    #     if (
    #         (score_np[i, j, match_way] > thr_ious_bev[cls_ind])
    #         and (i not in match_i)
    #         and (j not in match_j)
    #     ):
    #         match_list.append((i, j))
    #         match_i.add(i)
    #         match_j.add(j)
    #         if is_type_strict:
    #             gt_box_bev = get_bev_box(single_gt_list[i])
    #             pre_box_bev = get_bev_box(single_pre_list[j])
    #             matched_gt_objs_lt[cls_ind].append(gt_box_bev)
    #             matched_pre_objs_lt[cls_ind].append(pre_box_bev)
    #         match_class_num_bev[cls_ind] += 1
    #         # match_class_num[cls_ind] += 1

    match_2D_list = []
    match_2D_i = set()
    match_2D_j = set()

    match_way = 2
    sorted_inds = np.argsort(score_np.reshape(-1, 3)[:, match_way])[::-1]
    for ind in sorted_inds:
        i = ind // pre_len
        j = ind % pre_len
        name = single_gt_list[i][0]
        cls_ind = current_class.index(name)
        if (
            (score_np[i, j, match_way] > thr_ious_2D[cls_ind])
            and (i not in match_2D_i)
            and (j not in match_2D_j)
        ):
            match_2D_list.append((i, j))
            match_2D_i.add(i)
            match_2D_j.add(j)
            match_class_num[cls_ind] += 1

    return


def get_gt_and_pre_list(
    current_class,
    type_conversion,
    gt_name_path,
    pre_filename_path,
    gt_class_num,
    pre_class_num,
    single_gt_list,
    single_pre_list,
):
    with open(gt_name_path, 'r') as f:
        data = f.readlines()
        for txt_result in data:
            line = txt_result.strip('\n').split(' ')
            line[0] = type_conversion[line[0]]
            name = line[0]
            if name not in current_class:
                continue
            cls_ind = current_class.index(name)
            # 统计Gt里的类别数量，只统计测试范围内样本数量
            cam_x = float(line[cam_x_ind])
            cam_z = float(line[cam_z_ind])
            truncated = float(line[truncated_ind])
            occluded = float(line[occluded_ind])
            box2d = get_2D_box(line)
            if cam_z < 0:
                continue
            if math.isclose(truncated, 1.0):
                continue
            if int(occluded) == 2:
                continue
            if truncated >= 0.9 and min(box2d[2:4]) <= 20: continue
            if min(box2d[2:4]) <= 8:
                continue
            if (
                (cam_z < ranges_GTs[cls_ind][0])
                or (cam_z > ranges_GTs[cls_ind][1])
                or (cam_x < ranges_GTs[cls_ind][2])
                or (cam_x > ranges_GTs[cls_ind][3])
            ):
                continue
            gt_class_num[cls_ind] += 1
            single_gt_list.append(line)

    # 统计pre里的类别数量
    if os.path.exists(pre_filename_path):  # 如果存在gt对应的预测txt文件
        with open(pre_filename_path, 'r') as ff:
            data = ff.readlines()
            for txt_result in data:
                line = txt_result.strip('\n').split(' ')
                name = line[0]
                if name not in current_class:
                    continue
                cls_ind = current_class.index(name)
                cam_x = float(line[cam_x_ind])
                cam_z = float(line[cam_z_ind])
                if (
                    (cam_z < ranges_GTs[cls_ind][0] - pre_range_extend_z)
                    or (cam_z > ranges_GTs[cls_ind][1] + pre_range_extend_z)
                    or (cam_x < ranges_GTs[cls_ind][2] - pre_range_extend_x)
                    or (cam_x > ranges_GTs[cls_ind][3] + pre_range_extend_x)
                ):
                    continue
                pre_class_num[cls_ind] += 1
                single_pre_list.append(line)


def get_recall_ind(match_num, gt_num):
    if gt_num != 0:
        return 100 * match_num / gt_num
    else:
        return 100


def get_precision_ind(match_num, pre_num):
    if pre_num != 0:
        return 100 * match_num / pre_num
    else:
        return 100


def get_F1score_ind(precision, recall):
    if precision == 0 and recall == 0:
        return 0
    else:
        return 2 * precision * recall / (precision + recall)


def sy_eval_bev(
    label_path, result_path, label_split_file, current_class, type_conversion
):
    logger = logging.getLogger("monoflex.eval")
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()  # StreamHandler是输出到控制台
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.info(
        "{} {} {} {} {}".format(
            label_path, result_path, label_split_file, current_class, type_conversion
        )
    )
    class_cnt = len(current_class)
    logger.info("number of classes = {}".format(class_cnt))

    gt_class_num = [0] * class_cnt
    pre_class_num = [0] * class_cnt
    matching_class_num = [0] * class_cnt
    matching_class_num_bev = [0] * class_cnt
    matching_class_num_notype = [0] * class_cnt
    matching_class_num_bev_notype = [0] * class_cnt
    matched_bev_gt_objs_lt = [
        [] for i in range(class_cnt)
    ]  # do not use [[]] * class_cnt because inner [] is same
    matched_bev_pre_objs_lt = [[] for i in range(class_cnt)]

    gt_list = [x.strip() for x in open(label_split_file).readlines()]
    for gt_number in gt_list:  # 以Gt文件为基准，遍历测试
        gt_filename = gt_number + '.txt'
        gt_name_path = os.path.join(label_path, gt_filename)
        pre_filename_path = os.path.join(result_path, gt_filename)

        single_pre_list = []
        single_gt_list = []

        get_gt_and_pre_list(
            # input
            current_class,
            type_conversion,
            gt_name_path,
            pre_filename_path,
            # output
            gt_class_num,
            pre_class_num,
            single_gt_list,
            single_pre_list,
        )

        compute_match_num2(
            # input
            current_class,
            single_gt_list,
            single_pre_list,
            # output
            matching_class_num,
            matching_class_num_bev,
            is_type_strict=True,
            matched_gt_objs_lt=matched_bev_gt_objs_lt,
            matched_pre_objs_lt=matched_bev_pre_objs_lt,
        )

        compute_match_num2(
            # input
            current_class,
            single_gt_list,
            single_pre_list,
            # output
            matching_class_num_notype,
            matching_class_num_bev_notype,
            is_type_strict=False,
        )

    logger.info(
        "{:24} {:>8} {:>8} {:>10} {:>10} {:>10} {:>10}".format(
            "Type", "GT_num", "Pre_num", "Match_num", "Recall", "Precision", "F1_score"
        )
    )

    cutting_line = "----------------------------------------------------------------------------------"
    format_str = "{:24} {:>8} {:>8} {:>10} {:>9.2f}% {:>9.2f}% {:>9.2f}%"

    display_classes = []
    cls_rc_list = []
    cls_rc_bev_list = []
    cls_pc_list = []
    cls_pc_bev_list = []
    cls_f1_list = []
    cls_f1_bev_list = []
    matched_bev_gt_objs_dsp_lt = []
    matched_bev_pre_objs_dsp_lt = []
    for i in range(class_cnt):
        if gt_class_num[i] < display_min_num:
            matching_class_num[i] -= matching_class_num[i]
            matching_class_num_bev[i] -= matching_class_num_bev[i]
            matching_class_num_notype[i] -= matching_class_num_notype[i]
            matching_class_num_bev_notype[i] -= matching_class_num_bev_notype[i]
            gt_class_num[i] -= gt_class_num[i]
            pre_class_num[i] -= pre_class_num[i]
            continue

        display_classes.append(current_class[i])
        matched_bev_gt_objs_dsp_lt.append(matched_bev_gt_objs_lt[i])
        matched_bev_pre_objs_dsp_lt.append(matched_bev_pre_objs_lt[i])

        recall = get_recall_ind(matching_class_num[i], gt_class_num[i])  # notype
        recall_bev = get_recall_ind(
            matching_class_num_bev[i], gt_class_num[i]
        )  # notype

        precision = get_precision_ind(matching_class_num[i], pre_class_num[i])
        precision_bev = get_precision_ind(matching_class_num_bev[i], pre_class_num[i])

        F1_score = get_F1score_ind(precision, recall)
        F1_score_bev = get_F1score_ind(precision_bev, recall_bev)

        cls_rc_list.append(recall)
        cls_rc_bev_list.append(recall_bev)
        cls_pc_list.append(precision)
        cls_pc_bev_list.append(precision_bev)
        cls_f1_list.append(F1_score)
        cls_f1_bev_list.append(F1_score_bev)

        class_name = current_class[i]
        class_name = class_name + "(" + str(ranges_GTs[i][1]) + "m)"

        logger.info(cutting_line)
        logger.info(
            format_str.format(
                class_name + "_bev",
                gt_class_num[i],
                pre_class_num[i],
                matching_class_num_bev[i],
                recall_bev,
                precision_bev,
                F1_score_bev,
            )
        )

        logger.info(
            format_str.format(
                class_name,
                gt_class_num[i],
                pre_class_num[i],
                matching_class_num[i],
                recall,
                precision,
                F1_score,
            )
        )

    gt_num = sum(gt_class_num)
    recall_all = get_recall_ind(sum(matching_class_num), gt_num)
    recall_all_bev = get_recall_ind(sum(matching_class_num_bev), gt_num)
    recall_all_notype = get_recall_ind(sum(matching_class_num_notype), gt_num)
    recall_all_bev_notype = get_recall_ind(sum(matching_class_num_bev_notype), gt_num)

    pre_num = sum(pre_class_num)
    precision_all = get_precision_ind(sum(matching_class_num), pre_num)
    precision_all_bev = get_precision_ind(sum(matching_class_num_bev), pre_num)
    precision_all_notype = get_precision_ind(sum(matching_class_num_notype), pre_num)
    precision_all_bev_notype = get_precision_ind(
        sum(matching_class_num_bev_notype), pre_num
    )

    F1_score_all = get_F1score_ind(precision_all, recall_all)
    F1_score_all_bev = get_F1score_ind(precision_all_bev, recall_all_bev)
    F1_score_all_notype = get_F1score_ind(precision_all_notype, recall_all_notype)
    F1_score_all_bev_notype = get_F1score_ind(
        precision_all_bev_notype, recall_all_bev_notype
    )

    logger.info(cutting_line)
    logger.info(
        format_str.format(
            "All_bev",
            sum(gt_class_num),
            sum(pre_class_num),
            sum(matching_class_num_bev),
            recall_all_bev,
            precision_all_bev,
            F1_score_all_bev,
        )
    )
    logger.info(
        format_str.format(
            "All",
            sum(gt_class_num),
            sum(pre_class_num),
            sum(matching_class_num),
            recall_all,
            precision_all,
            F1_score_all,
        )
    )
    logger.info(cutting_line)
    logger.info(
        format_str.format(
            "All_bev_notype",
            sum(gt_class_num),
            sum(pre_class_num),
            sum(matching_class_num_bev_notype),
            recall_all_bev_notype,
            precision_all_bev_notype,
            F1_score_all_bev_notype,
        )
    )
    logger.info(
        format_str.format(
            "All_notype",
            sum(gt_class_num),
            sum(pre_class_num),
            sum(matching_class_num_notype),
            recall_all_notype,
            precision_all_notype,
            F1_score_all_notype,
        )
    )

    return (
        F1_score_all_bev,
        F1_score_all,
        recall_all_bev,
        recall_all,
        precision_all_bev,
        precision_all,
        F1_score_all_bev_notype,
        F1_score_all_notype,
        recall_all_bev_notype,
        recall_all_notype,
        precision_all_bev_notype,
        precision_all_notype,
        display_classes,
        cls_f1_list,
        cls_f1_bev_list,
        cls_rc_list,
        cls_rc_bev_list,
        cls_pc_list,
        cls_pc_bev_list,
        matched_bev_gt_objs_dsp_lt,
        matched_bev_pre_objs_dsp_lt,
    )


def main():
    # sy_eval_bev(
    #     "/home/zouhui/Works/Datasets/henggang_dataset/training/label_2_val",
    #     "/Works/3D_Object_Detect/MonoFlex/output/toy_experiments/inference/kitti_train/data",
    #     "/home/zouhui/Works/Datasets/henggang_dataset/training/ImageSets/val.txt",
    #     cfg.DATASETS.DETECT_CLASSES,
    #     "R40",
    # )

    eval_data_dir = "../MonoFlex_eval/"
    total_dirs = os.listdir(eval_data_dir)  # 获得目录下所有文件
    total_dirs = [
        total_dirs[i] for i in range(len(total_dirs)) if total_dirs[i][0] == '2'
    ]
    total_dirs.sort()
    total_ver_dcrpt = []
    f1_bev_list = []
    f1_2D_list = []
    rc_bev_list = []
    rc_2D_list = []
    pc_bev_list = []
    pc_2D_list = []
    f1_bev_notype_list = []
    f1_2D_notype_list = []
    rc_bev_notype_list = []
    rc_2D_notype_list = []
    pc_bev_notype_list = []
    pc_2D_notype_list = []
    dsp_cls_lt = []
    all_dsp_clses = []
    cls_f1_lt_lt = []
    cls_f1_bev_lt_lt = []
    cls_rc_lt_lt = []
    cls_rc_bev_lt_lt = []
    cls_pc_lt_lt = []
    cls_pc_bev_lt_lt = []

    for eval_once in total_dirs:  # get the eval results of every version of model
        print("processing " + eval_once)
        with open(os.path.join(eval_data_dir, eval_once, "type_tuple.txt")) as fp:
            content = fp.read()
            det_classes = eval(content)

        with open(
            os.path.join(eval_data_dir, eval_once, "type_convert_dict.txt")
        ) as fp:
            content = fp.read()
            type_conversion = eval(content)

        with open(
            os.path.join(eval_data_dir, eval_once, "xticks_description.txt")
        ) as fp:
            content = fp.read()
            total_ver_dcrpt.append(eval_once + "\n" + eval(content))

        (
            f1_bev,
            f1_2D,
            rc_bev,
            rc_2D,
            pc_bev,
            pc_2D,
            f1_bev_notype,
            f1_2D_notype,
            rc_bev_notype,
            rc_2D_notype,
            pc_bev_notype,
            pc_2D_notype,
            dsp_cls,
            cls_f1_lt,
            cls_f1_bev_lt,
            cls_rc_lt,
            cls_rc_bev_lt,
            cls_pc_lt,
            cls_pc_bev_lt,
            matched_bev_gt_objs_lt,
            matched_bev_pre_objs_lt,
        ) = sy_eval_bev(
            os.path.join(eval_data_dir, eval_once, "labels_data/label_2_val"),
            os.path.join(eval_data_dir, eval_once, "infer_files"),
            os.path.join(eval_data_dir, eval_once, "labels_data/val.txt"),
            det_classes,
            type_conversion,
        )
        f1_bev_list.append(f1_bev)
        f1_2D_list.append(f1_2D)
        rc_bev_list.append(rc_bev)
        rc_2D_list.append(rc_2D)
        pc_bev_list.append(pc_bev)
        pc_2D_list.append(pc_2D)

        f1_bev_notype_list.append(f1_bev_notype)
        f1_2D_notype_list.append(f1_2D_notype)
        rc_bev_notype_list.append(rc_bev_notype)
        rc_2D_notype_list.append(rc_2D_notype)
        pc_bev_notype_list.append(pc_bev_notype)
        pc_2D_notype_list.append(pc_2D_notype)

        dsp_cls_lt.append(dsp_cls)
        all_dsp_clses.extend([i for i in dsp_cls if not i in all_dsp_clses])
        cls_f1_lt_lt.append(cls_f1_lt)
        cls_f1_bev_lt_lt.append(cls_f1_bev_lt)
        cls_rc_lt_lt.append(cls_rc_lt)
        cls_rc_bev_lt_lt.append(cls_rc_bev_lt)
        cls_pc_lt_lt.append(cls_pc_lt)
        cls_pc_bev_lt_lt.append(cls_pc_bev_lt)

        gd_dsp_cls = dsp_cls
        gd_matched_bev_gt_objs_lt = matched_bev_gt_objs_lt
        gd_matched_bev_pre_objs_lt = matched_bev_pre_objs_lt

    eval_visual(
        total_ver_dcrpt,
        [
            f1_bev_notype_list,
            rc_bev_notype_list,
            pc_bev_notype_list,
            f1_2D_notype_list,
            rc_2D_notype_list,
            pc_2D_notype_list,
        ],
        [f1_bev_list, rc_bev_list, pc_bev_list, f1_2D_list, rc_2D_list, pc_2D_list],
        all_dsp_clses,
        dsp_cls_lt,
        cls_f1_bev_lt_lt,
        cls_rc_bev_lt_lt,
        cls_pc_bev_lt_lt,
        gd_matched_bev_gt_objs_lt,
        gd_matched_bev_pre_objs_lt,
        gd_dsp_cls,
        is_lidar=False,
        cls_f1_lt_lt=cls_f1_lt_lt,
        cls_rc_lt_lt=cls_rc_lt_lt,
        cls_pc_lt_lt=cls_pc_lt_lt,
    )


# 不同距离范围指标变化
# 角度循环
# 召回率
# 差异比例
# 标签朝向预处理（锥桶）
# 报告~~

if __name__ == '__main__':
    main()

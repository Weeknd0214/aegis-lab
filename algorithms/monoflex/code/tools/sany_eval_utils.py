import datetime
import os
import cv2
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def evaluate(box1, box2):
    '''

    :param box1: [z,x,l,w,angle]
    :param box2: [z,x,l,w,angle]
    :return: IOU_Scores
    '''

    area1 = abs((box1[2]) * (box1[3]))
    area2 = abs((box2[2]) * (box2[3]))
    area_sum = area1 + area2

    r1 = ((box1[0], box1[1]), (box1[2], box1[3]), box1[4])
    r2 = ((box2[0], box2[1]), (box2[2], box2[3]), box2[4])

    int_pts = cv2.rotatedRectangleIntersection(r1, r2)[1]
    if int_pts is not None:
        order_pts = cv2.convexHull(int_pts, returnPoints=True)
        int_area = cv2.contourArea(order_pts)
        ious = int_area * 1.0 / (area_sum - int_area)
    else:
        ious = 0

    return ious


# 顶点象限顺序(3, 4, 1, 2) for camera, (4, 3, 2, 1) for lidar
def get_order_corners(bev_corners):
    obj_cnt = bev_corners.shape[0]
    order_corners = np.zeros((obj_cnt, 4, 2), dtype=np.float32)
    for n in range(obj_cnt):
        for i in range(4):
            x = bev_corners[n, i, 0]
            y = bev_corners[n, i, 1]
            if x <= 0 and y < 0:
                index = 0
            elif x <= 0 and y >= 0:
                index = 1
            elif x > 0 and y >= 0:
                index = 2
            elif x > 0 and y < 0:
                index = 3
            order_corners[n, index, :] = bev_corners[n, i, :]
    return order_corners


def add_corners(box_np):  # (z, x, l, w, yaw) for camera, (x, y, l, w, yaw) for lidar
    # bev_corners = np.zeros((4, 2), dtype=np.float32)
    obj_cnt = box_np.shape[0]
    bev_corners = np.zeros((obj_cnt, 4, 2), dtype=np.float32)
    # x = box_np[:, 0]
    # y = box_np[:, 1]
    l = box_np[:, 2]
    w = box_np[:, 3]
    cos_yaw = np.cos(box_np[:, 4])
    sin_yaw = np.sin(box_np[:, 4])

    bev_corners[:, 0, 0] = (-l / 2) * cos_yaw - (w / 2) * sin_yaw
    bev_corners[:, 0, 1] = (w / 2) * cos_yaw + (-l / 2) * sin_yaw

    bev_corners[:, 1, 0] = (-l / 2) * cos_yaw - (-w / 2) * sin_yaw
    bev_corners[:, 1, 1] = (-w / 2) * cos_yaw + (-l / 2) * sin_yaw

    bev_corners[:, 2, 0] = (l / 2) * cos_yaw - (-w / 2) * sin_yaw
    bev_corners[:, 2, 1] = (-w / 2) * cos_yaw + (l / 2) * sin_yaw

    bev_corners[:, 3, 0] = (l / 2) * cos_yaw - (w / 2) * sin_yaw
    bev_corners[:, 3, 1] = (w / 2) * cos_yaw + (l / 2) * sin_yaw

    order_corners = get_order_corners(bev_corners)
    order_corners += np.expand_dims(box_np[:, 0:2], axis=1)
    box_corners = np.concatenate((box_np, order_corners.reshape(-1, 8)), axis=1)

    return box_corners


def get_diff_comb_array(a, b):
    matched_bev_gt_objs_all_np = np.array(a)
    matched_bev_gt_objs_all_np = add_corners(matched_bev_gt_objs_all_np)
    matched_bev_gt_objs_all_np[:, 4] -= (
        np.floor(matched_bev_gt_objs_all_np[:, 4] / 180.0) * 180
    )
    matched_bev_pre_objs_all_np = np.array(b)
    matched_bev_pre_objs_all_np = add_corners(matched_bev_pre_objs_all_np)
    matched_bev_pre_objs_all_np[:, 4] -= (
        np.floor(matched_bev_pre_objs_all_np[:, 4] / 180.0) * 180
    )
    matched_bev_objs_diff_np = np.abs(
        matched_bev_gt_objs_all_np - matched_bev_pre_objs_all_np
    )
    matched_bev_objs_diff_np[:, 4] -= (
        np.floor(matched_bev_objs_diff_np[:, 4] / 180.0) * 180
    )
    return np.stack(
        (
            matched_bev_gt_objs_all_np,
            matched_bev_pre_objs_all_np,
            matched_bev_objs_diff_np,
        ),
        axis=1,
    )


def sort_objs_by_data_dim(np_array, data_ind, dim_ind):
    sorted_inds = np.argsort(np_array[:, data_ind, dim_ind])
    return np_array[sorted_inds, :, :]


def eval_visual(
    total_dirs,
    f1_rc_pc_notype_list,
    f1_rc_pc_list,
    all_dsp_clses,
    dsp_cls_lt,
    cls_f1_bev_lt_lt,
    cls_rc_bev_lt_lt,
    cls_pc_bev_lt_lt,
    gd_matched_bev_gt_objs_lt,
    gd_matched_bev_pre_objs_lt,
    gd_dsp_cls,
    is_lidar=False,
    cls_f1_lt_lt=None,
    cls_rc_lt_lt=None,
    cls_pc_lt_lt=None,
):
    com_figsize = (16, 8)

    # 显示历史版本总体召回率、准确率、F1指标
    fig, ax = plt.subplots(1, 2, figsize=com_figsize, layout='constrained')
    ax[0].plot(total_dirs, f1_rc_pc_notype_list[0], '.--r', label='BEV_F1_Score')
    ax[0].plot(total_dirs, f1_rc_pc_notype_list[1], '.--g', label='BEV_recall')
    ax[0].plot(total_dirs, f1_rc_pc_notype_list[2], '.--b', label='BEV_precision')
    if not is_lidar:
        ax[0].plot(total_dirs, f1_rc_pc_notype_list[3], '.-r', label='2D_F1_Score')
        ax[0].plot(total_dirs, f1_rc_pc_notype_list[4], '.-g', label='2D_recall')
        ax[0].plot(total_dirs, f1_rc_pc_notype_list[5], '.-b', label='2D_precision')
    ax[0].set_title('Evaluation Index (notype)')
    ax[0].set_xlabel("Model Version and Data Size")
    ax[0].set_ylabel("Percentage")
    ax[0].set_ylim(0, 100)
    ax[0].grid(True)
    ax[0].legend()

    ax[1].plot(total_dirs, f1_rc_pc_list[0], '.--r', label='BEV_F1_Score')
    ax[1].plot(total_dirs, f1_rc_pc_list[1], '.--g', label='BEV_recall')
    ax[1].plot(total_dirs, f1_rc_pc_list[2], '.--b', label='BEV_precision')
    if not is_lidar:
        ax[1].plot(total_dirs, f1_rc_pc_list[3], '.-r', label='2D_F1_Score')
        ax[1].plot(total_dirs, f1_rc_pc_list[4], '.-g', label='2D_recall')
        ax[1].plot(total_dirs, f1_rc_pc_list[5], '.-b', label='2D_precision')
    ax[1].set_title('Evaluation Index (type strict)')
    ax[1].set_xlabel("Model Version and Data Size")
    ax[1].set_ylabel("Percentage")
    ax[1].set_ylim(0, 100)
    ax[1].grid(True)
    ax[1].legend()

    plt.show()

    print("all_dsp_clses = ", all_dsp_clses)
    # 分类别显示历史版本召回率、准确率、F1指标
    rows = 2
    cols = 4
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for i in range(len(all_dsp_clses)):
        finding_cls = all_dsp_clses[i]
        has_cls_dir = []
        has_cls_f1_lt = []
        has_cls_f1_bev_lt = []
        has_cls_rc_lt = []
        has_cls_rc_bev_lt = []
        has_cls_pc_lt = []
        has_cls_pc_bev_lt = []
        for j in range(
            len(dsp_cls_lt)
        ):  # get the model versions which has corresponding class
            if finding_cls in dsp_cls_lt[j]:
                has_cls_dir.append(total_dirs[j])
                has_cls_f1_bev_lt.append(
                    cls_f1_bev_lt_lt[j][dsp_cls_lt[j].index(finding_cls)]
                )
                has_cls_rc_bev_lt.append(
                    cls_rc_bev_lt_lt[j][dsp_cls_lt[j].index(finding_cls)]
                )
                has_cls_pc_bev_lt.append(
                    cls_pc_bev_lt_lt[j][dsp_cls_lt[j].index(finding_cls)]
                )
                if not is_lidar:
                    has_cls_f1_lt.append(
                        cls_f1_lt_lt[j][dsp_cls_lt[j].index(finding_cls)]
                    )
                    has_cls_rc_lt.append(
                        cls_rc_lt_lt[j][dsp_cls_lt[j].index(finding_cls)]
                    )
                    has_cls_pc_lt.append(
                        cls_pc_lt_lt[j][dsp_cls_lt[j].index(finding_cls)]
                    )
        axing = ax[i // cols, i % cols]
        axing.plot(has_cls_dir, has_cls_f1_bev_lt, '.--r', label='BEV_F1_Score')
        axing.plot(has_cls_dir, has_cls_rc_bev_lt, '.--g', label='BEV_recall')
        axing.plot(has_cls_dir, has_cls_pc_bev_lt, '.--b', label='BEV_precision')
        if not is_lidar:
            axing.plot(has_cls_dir, has_cls_f1_lt, '.-r', label='2D_F1_Score')
            axing.plot(has_cls_dir, has_cls_rc_lt, '.-g', label='2D_recall')
            axing.plot(has_cls_dir, has_cls_pc_lt, '.-b', label='2D_precision')
        axing.set_title(finding_cls)
        axing.set_xlabel("Model Version and Data Size")
        axing.set_ylabel("Percentage")
        axing.set_ylim(0, 100)
        axing.grid(True)
        axing.legend()
    plt.show()

    if not is_lidar:
        dsp_items = (
            "Z_Cam_Coord_Diff",
            "X-Cam-Coord_Diff",
            "Obj_Length_Diff",
            "Obj_Width_Diff",
            "Obj_Angle_Diff",
            "Obj_Height_Diff",
        )
    else:
        dsp_items = (
            "X_Lidar_Coord_Diff",
            "Y_Lidar_Coord_Diff",
            "Obj_Length_Diff",
            "Obj_Width_Diff",
            "Obj_Angle_Diff",
            "Obj_Height_Diff",
        )
    vertex_items = (
        "Vertex_0_X_Diff",
        "Vertex_0_Y_Diff",
        "Vertex_1_X_Diff",
        "Vertex_1_Y_Diff",
        "Vertex_2_X_Diff",
        "Vertex_2_Y_Diff",
        "Vertex_3_X_Diff",
        "Vertex_3_Y_Diff",
    )
    dsp_ylabel = (
        "distance(m)",
        "distance(m)",
        "length(m)",
        "width(m)",
        "angle(degree)",
        "height(m)",
    )
    matched_bev_gt_objs_all = []
    matched_bev_gt_objs_cls_num = [0]
    for i in range(len(gd_matched_bev_gt_objs_lt)):
        matched_bev_gt_objs_all.extend(gd_matched_bev_gt_objs_lt[i])
        # if len(matched_bev_gt_objs_cls_num) == 0:
        #     matched_bev_gt_objs_cls_num.append(len(gd_matched_bev_gt_objs_lt[i]))
        # else:
        matched_bev_gt_objs_cls_num.append(
            len(gd_matched_bev_gt_objs_lt[i]) + matched_bev_gt_objs_cls_num[-1]
        )
    matched_bev_pre_objs_all = []
    for i in range(len(gd_matched_bev_pre_objs_lt)):
        matched_bev_pre_objs_all.extend(gd_matched_bev_pre_objs_lt[i])

    # 计算真值与预测值的误差
    zipped_objs = get_diff_comb_array(matched_bev_gt_objs_all, matched_bev_pre_objs_all)
    objs_cnt = zipped_objs.shape[0]
    hist_yticks = np.linspace(0, objs_cnt, 11, endpoint=True)
    hist_ylabels = np.around(np.linspace(0, 1, 11, endpoint=True), decimals=1)
    print(hist_yticks)
    print(hist_ylabels)
    print(zipped_objs.shape)

    # （不分类别）观察目标3D各维度差异（升序）
    rows = 2
    cols = 3
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for i in range(len(dsp_items)):
        sort_zipped_objs_np = sort_objs_by_data_dim(zipped_objs, 0, i)
        axing = ax[i // cols, i % cols]
        axing.scatter(
            range(np.shape(sort_zipped_objs_np)[0]),
            sort_zipped_objs_np[:, 0, i],
            s=6,
            alpha=0.5,
            label="Ground_Truth",
        )
        axing.scatter(
            range(np.shape(sort_zipped_objs_np)[0]),
            sort_zipped_objs_np[:, 1, i],
            s=6,
            alpha=0.5,
            label="Prediction",
        )
        axing.scatter(
            range(np.shape(sort_zipped_objs_np)[0]),
            sort_zipped_objs_np[:, 2, i],
            s=6,
            alpha=0.5,
            label="Difference",
        )
        axing.set_xlabel("objs numbers")
        axing.set_ylabel(dsp_ylabel[i])
        axing.set_title(dsp_items[i])
        axing.legend()
        axing.grid(True)
    plt.show()

    # （不分类别）观察目标3D各维度差异的直方图分布
    rows = 2
    cols = 3
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for i in range(len(dsp_items)):
        axing = ax[i // cols, i % cols]
        print("{} average = {:.2f}".format(dsp_items[i], np.mean(zipped_objs[:, 2, i])))
        hist_num_seq, _, _ = axing.hist(zipped_objs[:, 2, i], 40)
        ylim = np.ceil(hist_num_seq.max() / objs_cnt * 10 + 0.1) / 10 * objs_cnt
        if ylim > objs_cnt:
            ylim = objs_cnt
        axing.set_xlabel(dsp_ylabel[i])
        axing.set_ylabel("Percentage")
        axing.set_title(dsp_items[i])
        axing.set_yticks(hist_yticks, hist_ylabels)
        axing.set_xlim(left=0, right=zipped_objs[:, 2, i].max())
        if dsp_items[i] == "Obj_Angle_Diff":
            axing.set_xlim(left=0, right=180)

        axing.set_ylim(top=ylim)
        axing.xaxis.set_major_locator(ticker.LinearLocator(11))
        if dsp_items[i] != "Obj_Angle_Diff":
            axing.xaxis.set_major_formatter(ticker.StrMethodFormatter("{x:.2f}"))

        axing.xaxis.set_minor_locator(ticker.LinearLocator(41))
        axing.grid(True)
    plt.show()

    # （不分类别）观察目标BEV的四个顶点差异（升序）
    rows = 2
    cols = 4
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for n in range(len(vertex_items)):
        i = n + len(dsp_items)
        sort_zipped_objs_np = sort_objs_by_data_dim(zipped_objs, 0, i)
        axing = ax[n // cols, n % cols]
        axing.scatter(
            range(np.shape(sort_zipped_objs_np)[0]),
            sort_zipped_objs_np[:, 0, i],
            s=6,
            alpha=0.5,
            label="Ground_Truth",
        )
        axing.scatter(
            range(np.shape(sort_zipped_objs_np)[0]),
            sort_zipped_objs_np[:, 1, i],
            s=6,
            alpha=0.5,
            label="Prediction",
        )
        axing.scatter(
            range(np.shape(sort_zipped_objs_np)[0]),
            sort_zipped_objs_np[:, 2, i],
            s=6,
            alpha=0.5,
            label="Difference",
        )
        axing.set_xlabel("objs numbers")
        axing.set_ylabel("distance(m)")
        axing.set_title(vertex_items[n])
        axing.legend()
        axing.grid(True)
    plt.show()

    # （不分类别）观察目标BEV的四个顶点差异的直方图分布
    rows = 2
    cols = 4
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for n in range(len(vertex_items)):
        i = n + len(dsp_items)
        axing = ax[n // cols, n % cols]
        print("{} average = {:.2f}".format(vertex_items[n], np.mean(zipped_objs[:, 2, i])))
        hist_num_seq, _, _ = axing.hist(zipped_objs[:, 2, i], 40)
        ylim = np.ceil(hist_num_seq.max() / objs_cnt * 10 + 0.1) / 10 * objs_cnt
        if ylim > objs_cnt:
            ylim = objs_cnt
        axing.set_xlabel("distance(m)")
        axing.set_ylabel("Percentage")
        axing.set_title(vertex_items[n])
        axing.set_yticks(hist_yticks, hist_ylabels)
        axing.xaxis.set_tick_params(labelrotation=60)
        axing.set_xlim(left=0, right=zipped_objs[:, 2, i].max())
        axing.set_ylim(top=ylim)
        axing.xaxis.set_major_locator(ticker.LinearLocator(11))
        axing.xaxis.set_major_formatter(ticker.StrMethodFormatter("{x:.2f}"))
        axing.xaxis.set_minor_locator(ticker.LinearLocator(41))
        axing.grid(True)
    plt.show()

    # 分类别观察目标3D各维度差异（升序）
    rows = 2
    cols = 3
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for i in range(len(dsp_items)):
        for j in range(len(gd_dsp_cls)):
            zipped_objs = get_diff_comb_array(
                gd_matched_bev_gt_objs_lt[j], gd_matched_bev_pre_objs_lt[j]
            )
            sort_zipped_objs_np = sort_objs_by_data_dim(zipped_objs, 0, i)
            axing = ax[i // cols, i % cols]
            class_range = np.arange(
                matched_bev_gt_objs_cls_num[j], matched_bev_gt_objs_cls_num[j + 1], 1
            )
            axing.scatter(
                class_range,
                sort_zipped_objs_np[:, 0, i],
                s=6,
                c='C0',
                alpha=0.5,
            )
            axing.scatter(
                class_range,
                sort_zipped_objs_np[:, 1, i],
                s=6,
                c='C1',
                alpha=0.5,
            )
            axing.scatter(
                class_range,
                sort_zipped_objs_np[:, 2, i],
                s=6,
                c='C2',
                alpha=0.5,
            )
        axing.set_xlabel("class name and objs numbers")
        axing.set_ylabel(dsp_ylabel[i])
        axing.set_title(dsp_items[i])
        axing.set_xticks(matched_bev_gt_objs_cls_num[1:])
        axing.set_xticklabels(gd_dsp_cls, rotation=60, fontsize='small')
        axing.grid(True)
    fig.legend(['Ground_Truth', 'Prediction', 'Difference'])
    plt.show()

    # 分类别观察目标3D各维度差异的直方图分布
    rows = 2
    cols = 3
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for i in range(len(dsp_items)):
        zipped_objs_lt = []
        for j in range(len(gd_dsp_cls)):
            zipped_objs = get_diff_comb_array(
                gd_matched_bev_gt_objs_lt[j], gd_matched_bev_pre_objs_lt[j]
            )
            print("{} {} average = {:.2f}".format(dsp_items[i], gd_dsp_cls[j], np.mean(zipped_objs[:, 2, i])))
            zipped_objs_lt.append(zipped_objs[:, 2, i])
        axing = ax[i // cols, i % cols]
        hist_num_seq, _, _ = axing.hist(zipped_objs_lt, 10, label=gd_dsp_cls)
        ylim = np.ceil(hist_num_seq.max() / objs_cnt * 10 + 0.1) / 10 * objs_cnt
        if ylim > objs_cnt:
            ylim = objs_cnt
        axing.set_xlabel(dsp_ylabel[i])
        axing.set_ylabel("Percentage")
        axing.set_title(dsp_items[i])
        axing.set_yticks(hist_yticks, hist_ylabels)
        axing.set_xlim(left=0, right=max([i.max() for i in zipped_objs_lt]))
        if dsp_items[i] == "Obj_Angle_Diff":
            axing.set_xlim(left=0, right=180)

        axing.set_ylim(top=ylim)
        axing.xaxis.set_major_locator(ticker.LinearLocator(11))
        if dsp_items[i] != "Obj_Angle_Diff":
            axing.xaxis.set_major_formatter(ticker.StrMethodFormatter("{x:.2f}"))

        axing.xaxis.set_minor_locator(ticker.LinearLocator(41))
        axing.grid(True)
        axing.legend()
    plt.show()

    # 分类别观察目标BEV的四个顶点差异（升序）
    rows = 2
    cols = 4
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for n in range(len(vertex_items)):
        i = n + len(dsp_items)
        for j in range(len(gd_dsp_cls)):
            zipped_objs = get_diff_comb_array(
                gd_matched_bev_gt_objs_lt[j], gd_matched_bev_pre_objs_lt[j]
            )
            sort_zipped_objs_np = sort_objs_by_data_dim(zipped_objs, 0, i)
            axing = ax[n // cols, n % cols]
            class_range = np.arange(
                matched_bev_gt_objs_cls_num[j], matched_bev_gt_objs_cls_num[j + 1], 1
            )
            axing.scatter(
                class_range,
                sort_zipped_objs_np[:, 0, i],
                s=6,
                c='C0',
                alpha=0.5,
            )
            axing.scatter(
                class_range,
                sort_zipped_objs_np[:, 1, i],
                s=6,
                c='C1',
                alpha=0.5,
            )
            axing.scatter(
                class_range,
                sort_zipped_objs_np[:, 2, i],
                s=6,
                c='C2',
                alpha=0.5,
            )
        axing.set_xlabel("class name and objs numbers")
        axing.set_ylabel("distance(m)")
        axing.set_title(vertex_items[n])
        axing.set_xticks(matched_bev_gt_objs_cls_num[1:])
        axing.set_xticklabels(gd_dsp_cls, rotation=60, fontsize='small')
        axing.grid(True)
    fig.legend(['Ground_Truth', 'Prediction', 'Difference'])
    plt.show()

    # 分类别观察目标BEV的四个顶点的直方图分布
    rows = 2
    cols = 4
    fig, ax = plt.subplots(rows, cols, figsize=com_figsize, layout='constrained')
    for n in range(len(vertex_items)):
        i = n + len(dsp_items)
        zipped_objs_lt = []
        for j in range(len(gd_dsp_cls)):
            zipped_objs = get_diff_comb_array(
                gd_matched_bev_gt_objs_lt[j], gd_matched_bev_pre_objs_lt[j]
            )
            print("{} {} average = {:.2f}".format(vertex_items[n], gd_dsp_cls[j], np.mean(zipped_objs[:, 2, i])))
            zipped_objs_lt.append(zipped_objs[:, 2, i])
        axing = ax[n // cols, n % cols]
        hist_num_seq, _, _ = axing.hist(zipped_objs_lt, 10, label=gd_dsp_cls)
        ylim = np.ceil(hist_num_seq.max() / objs_cnt * 10 + 0.1) / 10 * objs_cnt
        if ylim > objs_cnt:
            ylim = objs_cnt
        axing.set_xlabel("distance(m)")
        axing.set_ylabel("Percentage")
        axing.set_title(vertex_items[n])
        axing.set_yticks(hist_yticks, hist_ylabels)
        axing.xaxis.set_tick_params(labelrotation=60)
        axing.set_xlim(left=0, right=max([i.max() for i in zipped_objs_lt]))
        axing.set_ylim(top=ylim)
        axing.xaxis.set_major_locator(ticker.LinearLocator(11))
        axing.xaxis.set_major_formatter(ticker.StrMethodFormatter("{x:.2f}"))
        axing.xaxis.set_minor_locator(ticker.LinearLocator(41))
        axing.grid(True)
        axing.legend()
    plt.show()

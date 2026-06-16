# !/usr/bin/python
# -*- coding: utf-8 -*-
"""
@File   :   融合可视化
@Time   :   2024/3/22 17:27
@Author :   wyr
@Version:   1.0.0
@contact:   wangyiren@testin.cn
@PM     :   None
@Desc   :   None
@host   :   https://label-std.testin.cn/
"""
import contextlib
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
from PIL import Image
from testin_export.tools.cloud.vis import show_image_pinhole


def get_box_points(x, y, z, length, width, height, roll, pitch, yaw, orientation=False):
    #                                         z     y
    #       5------------4                    |   /
    #      /|           /|                    |  /
    #     3------------6 |                    | /
    #     | |          | |           ----------------->x
    #     | |          | |                   /|
    #     | 2----------|-7                  / |
    #     |/           |/
    #     0------------1
    if orientation:
        return _ten_points(x, y, z, length, width, height, roll, pitch, yaw)
    else:
        return _eight_points(x, y, z, length, width, height, roll, pitch, yaw)


def _get_obb(x, y, z, length, width, height, roll, pitch, yaw):
    obb = o3d.geometry.OrientedBoundingBox()
    obb.extent = np.array([length, width, height], np.float32)
    obb.R = o3d.geometry.get_rotation_matrix_from_xyz((roll, pitch, yaw))
    obb.center = np.array([x, y, z], np.float32)
    return obb


def _eight_points(x, y, z, length, width, height, roll, pitch, yaw):
    obb = _get_obb(x, y, z, length, width, height, roll, pitch, yaw)
    return np.asarray(obb.get_box_points())


def _ten_points(x, y, z, length, width, height, roll, pitch, yaw):
    obb = _get_obb(0, 0, 0, length, width, height, 0, 0, 0)
    pts = np.asarray(obb.get_box_points())
    arrow = np.array(
        [[0, 0, 0], [length * 0.75, 0, 0]],
        np.float32,
    )
    pts = np.vstack((pts, arrow))
    rotation_matrix = o3d.geometry.get_rotation_matrix_from_xyz((roll, pitch, yaw))
    pts = rotation_matrix.dot(pts.T).T
    pts[:, 0] += x
    pts[:, 1] += y
    pts[:, 2] += z
    return pts


class _Pts(object):
    def __init__(self, cloud=None, boxes=None):
        self.cloud = cloud
        self.boxes = boxes


def _draw_image_box(box, img):
    on_image = 0
    h, w = img.shape[:2]
    for pt in box:
        if pt[2] < 0:
            return
        if abs(pt[0] / w) > 2 or abs(pt[1] / h) > 2:
            return
        if 0 <= pt[0] < w and 0 <= pt[1] < h:
            on_image += 1
    if on_image < 2:
        return
    cv2.line(
        img,
        np.array([box[0, 0], box[0, 1]], np.int32),
        np.array([box[1, 0], box[1, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[1, 0], box[1, 1]], np.int32),
        np.array([box[7, 0], box[7, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[7, 0], box[7, 1]], np.int32),
        np.array([box[2, 0], box[2, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[2, 0], box[2, 1]], np.int32),
        np.array([box[0, 0], box[0, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[3, 0], box[3, 1]], np.int32),
        np.array([box[6, 0], box[6, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[6, 0], box[6, 1]], np.int32),
        np.array([box[4, 0], box[4, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[4, 0], box[4, 1]], np.int32),
        np.array([box[5, 0], box[5, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[5, 0], box[5, 1]], np.int32),
        np.array([box[3, 0], box[3, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[0, 0], box[0, 1]], np.int32),
        np.array([box[3, 0], box[3, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[1, 0], box[1, 1]], np.int32),
        np.array([box[6, 0], box[6, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[7, 0], box[7, 1]], np.int32),
        np.array([box[4, 0], box[4, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.line(
        img,
        np.array([box[2, 0], box[2, 1]], np.int32),
        np.array([box[5, 0], box[5, 1]], np.int32),
        (0, 0, 255),
        1,
    )
    cv2.fillPoly(
        img,
        [
            np.array(
                [
                    [box[6, 0], box[6, 1]],
                    [box[1, 0], box[1, 1]],
                    [box[7, 0], box[7, 1]],
                    [box[4, 0], box[4, 1]],
                ],
                np.int32,
            )
        ],
        (0, 0, 255),
    )


@contextlib.contextmanager
def _show_image_base(
    pcd,
    img,  # cv2 img np.array object
    boxes=None,
    show=True,
    save_root=None,
):
    # if isinstance(pcd, str):
    #     pcd = read_point_cloud(pcd)
    # if not hasattr(pcd, "to_legacy"):
    #     pcd = o3d.t.geometry.PointCloud().from_legacy(pcd)
    # if isinstance(img, str):
    #     img = read_image(img)
    # elif isinstance(img, PIL.Image.Image):
    #     img = to_array(img)
    if boxes:
        box_pts = [get_box_points(*box) for box in boxes]
        box_pts = np.concatenate(box_pts, axis=0)
    else:
        box_pts = None

    pts = _Pts(pcd.point["positions"].numpy(), box_pts)

    yield pts

    # for pt in pts.cloud[np.where(pts.cloud[:, 2] >= 0)]:
    #     color = _get_depth(float(pt[2]))
    #     cv2.circle(img, np.asarray(pt[:2], np.int32), 1, color, -1)

    if pts.boxes is not None:
        for box in pts.boxes.reshape(-1, 8, 3):
            _draw_image_box(box, img)

    image = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if show:
        image.show()
    if save_root is not None:
        Path(save_root).parent.mkdir(parents=True, exist_ok=True)
        image.save(save_root)


def pinhole(pcd, extrinsic, intrinsic, distortion=None):
    if isinstance(pcd, np.ndarray):
        pts = np.dot(pcd, extrinsic[:3, :3].T)
        pts += extrinsic[:3, 3]
    else:
        pcd = pcd.transform(extrinsic)
        pts = np.asarray(pcd.point["positions"].numpy(), np.float32)

    x = pts[:, 0] / pts[:, 2]
    y = pts[:, 1] / pts[:, 2]

    if distortion is None:
        distortion = np.zeros(12)
    ks = np.zeros(12)
    distortion = np.asarray(distortion)
    ks[: distortion.size] = distortion

    r2 = x * x + y * y
    k1r2 = ks[0] * r2
    k2r4 = ks[1] * r2 * r2
    k3r6 = ks[4] * r2 * r2 * r2
    k4r2 = ks[5] * r2
    k5r4 = ks[6] * r2 * r2
    k6r6 = ks[7] * r2 * r2 * r2
    p1 = ks[2]
    p2 = ks[3]
    s1r2 = ks[8] * r2
    s2r4 = ks[9] * r2 * r2
    s3r2 = ks[10] * r2
    s4r4 = ks[11] * r2 * r2

    a1 = 2 * x * y
    a2 = r2 + 2 * x * x
    a3 = r2 + 2 * y * y

    c1 = 1 + k1r2 + k2r4 + k3r6
    c2 = 1 / (1 + k4r2 + k5r4 + k6r6)

    dx = x * c1 * c2 + p1 * a1 + p2 * a2 + s1r2 + s2r4
    dy = y * c1 * c2 + p1 * a3 + p2 * a1 + s3r2 + s4r4

    fx, fy, cx, cy = intrinsic
    u = dx * fx + cx
    v = dy * fy + cy

    pts[:, 0] = u
    pts[:, 1] = v
    return pts


def show_image_pinhole(
    pcd,
    img,
    extrinsic,
    intrinsic,
    distortion=None,
    boxes=None,
    show=True,
    save_root=None,
):
    """
    project point cloud onto the pinhole image
    :param pcd: pcd file path, o3d.geometry.PointCloud object, o3d.t.geometry.PointCloud object
    :param img: image file path, PIL.Image object, img array
    :param extrinsic: list: ┌                  ┐
                            │ R(3, 3), T(3, 1) │
                            │ 0(1, 3), 1(1, 1) │
                            └                  ┘
    :param intrinsic: list: [fx, fy, cx, cy]
    :param distortion: list: [k1, k2, p1, p2, k3, k4, k5, k6, s1, s2, s3, s4]
                       missing parameters can be empty or filled with zero
    :param boxes: list: [
                            [x, y, z, l, w, h, rx, ry, rz],
                            ...,
                        ]
    :param show: visualize image object
    :param save_root: image save path
    """
    with _show_image_base(pcd, img, boxes, show, save_root) as pts:
        pts.cloud = pinhole(pts.cloud, np.asarray(extrinsic), intrinsic, distortion)
        if pts.boxes is not None:
            pts.boxes = pinhole(pts.boxes, np.asarray(extrinsic), intrinsic, distortion)


def vis(pcd, img, txt, params, out=None):
    extrinsic = params["extrinsic"]
    intrinsic = [params["fx"], params["fy"], params["cx"], params["cy"]]
    distortion = [params["k1"], params["k2"], params["p1"], params["p2"], params["k3"]]

    boxes = []
    with open(txt, encoding="utf-8") as f:
        for line in f.readlines():
            if line.strip():
                line = line.strip().split(" ")
                h = float(line[7])
                w = float(line[8])
                l = float(line[9])
                x = float(line[16])
                y = float(line[17])
                z = float(line[18])
                roll = float(line[19])
                pitch = float(line[20])
                yaw = float(line[21])
                boxes.append([x, y, z, l, w, h, roll, pitch, yaw])

    show_image_pinhole(pcd, img, np.eye(4), intrinsic, distortion, boxes)

    # js = Path(txt).with_suffix(".json")
    # boxes = []
    # with open(js, encoding="utf-8") as f:
    #     info = json.load(f)
    #     for label in info["lidar"]:
    #         x = label["annotation"]["data"]["position"]["x"]
    #         y = label["annotation"]["data"]["position"]["y"]
    #         z = label["annotation"]["data"]["position"]["z"]
    #         h = label["annotation"]["data"]["dimension"]["h"]
    #         w = label["annotation"]["data"]["dimension"]["w"]
    #         l = label["annotation"]["data"]["dimension"]["l"]
    #         rx = label["annotation"]["data"]["rotation"]["x"]
    #         ry = label["annotation"]["data"]["rotation"]["y"]
    #         rz = label["annotation"]["data"]["rotation"]["z"]
    #         boxes.append([x, y, z, l, w, h, rx, ry, rz])
    #
    # show_image_pinhole(pcd, img, extrinsic, intrinsic, distortion, boxes)


if __name__ == "__main__":
    pcd_file = r"D:\work\data\test\00038\lidar\hg_rear_2539_20220421210201_505.pcd"
    img_file = (
        r"D:\work\data\test\00038\camera\camera0\hg_rear_2539_20220421210201_505.jpg"
    )
    txt_file = r"D:\work\data\test\240126a4c4e\2401261970\label_datas_240112_rear\00038\hg_rear_2539_20220421210201_505.txt"
    pp = {
        "camera_model": "pinhole",
        "extrinsic": [
            [
                -0.03301197804940615,
                0.9994072534231899,
                -0.009764789315786199,
                -0.07138674357806221,
            ],
            [
                0.07854876292064075,
                -0.007145554179479822,
                -0.9968846637897011,
                -0.9398936044141779,
            ],
            [
                -0.9963635386488727,
                -0.03367614675975107,
                -0.07826631453258316,
                -1.631814248652888,
            ],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "fx": 1646.6064453125,
        "fy": 1859.481201171875,
        "cx": 1000.191546430869,
        "cy": 548.8399188917538,
        "k1": 0,
        "k2": 0,
        "p1": 0,
        "p2": 0,
        "k3": 0,
    }
    vis(pcd_file, img_file, txt_file, pp)

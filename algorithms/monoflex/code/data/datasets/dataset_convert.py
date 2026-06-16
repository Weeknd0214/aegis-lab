import os
import re
import csv



def generate_kitti_3d_detection(prediction, predict_txt):

    # ID_TYPE_CONVERSION = {
    #     0: 'Truck',
    #     1: 'Car',
    #     2: 'Van',
    #     3: 'Pedestrian',
    #     4: 'Cyclist'
    # }

    with open(predict_txt, 'w', newline='') as f:
        w = csv.writer(f, delimiter=' ', lineterminator='\n')
        if len(prediction) == 0:
            w.writerow([])
        else:
            for p in prediction:
                # p = p.numpy()
                # p = p.round(4)
                # type = ID_TYPE_CONVERSION[int(p[0])]
                # row = [type, 0, 0] + p[1:].tolist()
                # w.writerow(row)
                w.writerow(p)

    check_last_line_break(predict_txt)

def check_last_line_break(predict_txt):
    f = open(predict_txt, 'rb+')
    try:
        f.seek(-1, os.SEEK_END)
    except:
        pass
    else:
        if f.__next__() == b'\n':
            f.seek(-1, os.SEEK_END)
            f.truncate()
    f.close()


class Object3d(object):
    """ 3d object label """

    def __init__(self, label_file_line, scale_ratio):
        data = label_file_line.split(" ")
        data[1:] = [float(x) for x in data[1:]]
        # extract label, truncation, occlusion
        self.type = data[0]  # 'Car', 'Pedestrian', ...
        self.truncation = data[1]  # truncated pixel ratio [0..1]
        self.occlusion = int(
            data[2]
        )  # 0=visible, 1=partly occluded, 2=fully occluded, 3=unknown

        # extract 2d bounding box in 0-based coordinates
        self.xmin = data[3]  # left
        self.ymin = data[4]  # top
        self.xmax = data[5]  # right
        self.ymax = data[6]  # bottom


if __name__ == '__main__':

    root_dir = "/home/sany/Works/Datasets/liangang_dataset_01_02"
    label_orig_dir = os.path.join(root_dir, "liangang_labels")
    label_cvt_dir = os.path.join(root_dir, "label_cvt")

    total_label_txt = os.listdir(label_orig_dir)
    print(total_label_txt)

    label_path_set = set()
    for root, dirs, files in os.walk(label_orig_dir):
        for name in files:
            # path_name = os.path.join(root, name)
            rem = re.match(".+\.txt", name)
            if rem:
                label_path_set.add(rem.group(0))

    # print(label_path_set)
    object_3D_count = 0
    object_2D_count = 0

    for name in label_path_set:
        label_orig_file = os.path.join(label_orig_dir, name)
        label_cvt_file = os.path.join(label_cvt_dir, name)
        print("")
        print("converting ", label_orig_file)
        # new_lines = list()
        lines = [line.rstrip() for line in open(label_orig_file)]
        object_3D_count +=len(lines)
        objects = [Object3d(line, 1.) for line in lines]

        objects_2D = [obj for obj in objects if not (obj.xmax < 0.01 and obj.xmin < 0.01 and obj.ymax < 0.01 and obj.ymin < 0.01)]
        object_2D_count += len(objects_2D)
        # print("lines = ", lines)
        # for line in lines:
        # 	new_lines.add(line)
        # generate_kitti_3d_detection(lines, label_cvt_file)

        # objects = [Object3d(line, scale_ratio) for line in lines]

    print("object_3D_count = ", object_3D_count)
    print("object_2D_count = ", object_2D_count)

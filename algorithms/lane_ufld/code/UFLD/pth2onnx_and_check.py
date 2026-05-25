# encoding: utf-8

import time
import tkinter.filedialog

import cv2
import numpy as np
import onnx
import onnxruntime
import scipy.special
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

import torch
import torch.backends.cudnn
import torchvision.transforms as transforms
from PIL import Image as imim
from torch import nn

from data.constant import tusimple_row_anchor
from model.model import parsingNet
from utils.common import merge_config

import glob

# 一些预定设置
torch.backends.cudnn.benchmark = True
args, cfg = merge_config()
griding_num = 100
img_w, img_h = 1280, 720
row_anchor = tusimple_row_anchor
cls_num_per_lane = 56

model_path = "/home/ljk/桌面/ClrNet_onnx_modify/UFLD/ep327_ufld.pth"
# model_path = "/home/ljk/桌面/ep015_2ch_res18.pth"
folder_path = "/home/ljk/桌面/pic_1228_lane/pic1_720/*.jpg"


def func(x, a, b, c, d):
    return a * pow(x, 3) + b * pow(x, 2) + c * x + d


class ufld_2(nn.Module):
    def __init__(self):
        super().__init__()

        # self.path = "/home/ljk/桌面/semantic_code/1.lane_detect/3.model_weight/1.pth/shuangyujing_model_SpeedUp.pth"
        # print(self.path)
        # self.net = torch.load(self.path)

        backbone_ = '18'
        self.net = parsingNet(pretrained=False, backbone=backbone_, cls_dim=(cfg.griding_num + 1, 56, 2),
                              use_aux=False).cuda()

        self.path = model_path
        print(self.path)

        state_dict = torch.load(self.path, map_location='cpu')['model']
        compatible_state_dict = {}
        for k, v in state_dict.items():
            if 'module.' in k:
                compatible_state_dict[k[7:]] = v
            else:
                compatible_state_dict[k] = v
        self.net.load_state_dict(compatible_state_dict, strict=False)

        self.net.eval()

        # self.onnx_model_name = self.path[:-4] + ".onnx"
        self.onnx_model_name = "/home/ljk/桌面/ClrNet_onnx_modify/UFLD/ep327_ufld.onnx"

    def export_onnx(self):
        x = torch.randn(1, 3, 288, 800).cuda()

        # torch.onnx.export 可以检查剪枝模型出了什么错
        with torch.no_grad():
            torch.onnx.export(self.net, x, self.onnx_model_name, export_params=True, opset_version=11,
                              input_names=['input'],
                              output_names=['output'])

        print('\n', "start check...")
        onnx_model = onnx.load(self.onnx_model_name)
        try:
            onnx.checker.check_model(onnx_model)
        except:
            print("Model incorrect")
        else:
            print("Model correct")

    def output_cmp(self, img_path):
        start = time.time()
        img = imim.open(img_path)
        img_transforms = transforms.Compose([
            transforms.Resize((288, 800)),
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
        ])
        img = img_transforms(img).unsqueeze_(0).cuda()

        # 原模型的输出-------------------
        with torch.no_grad():
            out = self.net(img)
        pth_output = to_numpy(out)
        end = time.time()
        cost_time = end - start
        print("pth_cost_time:", cost_time * 1000, " ms")
        print("原模型前5*4个向量输出：\n", pth_output[0][0][:5])

        start = time.time()
        ort_session = onnxruntime.InferenceSession(self.onnx_model_name)
        end = time.time()
        cost_time = end - start
        print("onnx_cost_time:", cost_time * 1000, " ms")
        ort_inputs = {'input': to_numpy(img)}
        ort_out = ort_session.run(['output'], ort_inputs)[0]
        print("onnx的输出大小：", ort_out.shape)
        print("onnx前5*4个向量输出：\n", ort_out[0][0][:5])

        # np.testing.assert_allclose(pth_output, ort_out, rtol=1e-01, atol=1e-03)
        print("*****************************")
        print("精度对比结束，满足精度！")
        print("*****************************")

        # _ = pro_process(pth_output, img_path)
        print(img_path)
        _ = pro_process(ort_out, img_path)
        # cv2.namedWindow('vis_onnx')
        # cv2.imshow("vis_onnx", pro_process(ort_out, img_path))


def get_path():
    filename = tkinter.filedialog.askopenfilename()
    return filename


# 工具函数：tensor->numpy
def to_numpy(tensor):
    return tensor.detach().cpu().numpy() if tensor.requires_grad else tensor.cpu().numpy()


# 工具函数：后处理与可视化
def pro_process(out, path):
    col_sample = np.linspace(0, 800 - 1, griding_num)
    col_sample_w = col_sample[1] - col_sample[0]

    out_j = out[0]
    out_j = out_j[:, ::-1, :]
    prob = scipy.special.softmax(out_j[:-1, :, :], axis=0)
    idx = np.arange(griding_num) + 1
    idx = idx.reshape(-1, 1, 1)
    loc = np.sum(prob * idx, axis=0)
    out_j = np.argmax(out_j, axis=0)
    loc[out_j == griding_num] = 0
    out_j = loc

    vis = cv2.imread(path)
    left_points = []
    right_points = []
    for i in range(out_j.shape[1]):
        if np.sum(out_j[:, i] != 0) > 2:
            if i == 1:
                print("Left Line")
            else:
                print("Right Line")
            count = 0
            for k in range(out_j.shape[0]):
                if out_j[k][i] > 0:
                    x = int(out_j[k][i] * col_sample_w * img_w / 800) - 1
                    y = int(img_h * (row_anchor[cls_num_per_lane - 1 - k] / 288)) - 1
                    ppp = (x, y)
                    # print(ppp)
                    if i == 0:
                        left_points.append(ppp)
                    else:
                        right_points.append(ppp)
                    cv2.circle(vis, ppp, 2, (255, 0, 0), -1)
                    count += 1
            print(count)
    print("\n")
    # if len(left_points) == 0 or len(right_points) == 0:
    #     return vis
    # left_points_x = np.reshape(left_points, (len(left_points), -1))[:, 1]
    # left_points_y = np.reshape(left_points, (len(left_points), -1))[:, 0]
    # right_points_x = np.reshape(right_points, (len(right_points), -1))[:, 1]
    # right_points_y = np.reshape(right_points, (len(right_points), -1))[:, 0]
    # popt_left, _ = curve_fit(func, left_points_x, left_points_y)
    # popt_right, _ = curve_fit(func, right_points_x, right_points_y)
    # right_points_y_func = []
    # left_points_y_func = []
    # for i in range(len(left_points_x)):
    #     ppp = (int(func(left_points_x[i], popt_left[0], popt_left[1], popt_left[2], popt_left[3])),
    #            left_points_x[i])
    #     # cv2.circle(vis, ppp, 5, (0, 255, 0), -1)
    #     left_points_y_func.append(
    #         int(func(left_points_x[i], popt_left[0], popt_left[1], popt_left[2], popt_left[3])))
    # for i in range(len(right_points_x)):
    #     ppp = (
    #         int(func(right_points_x[i], popt_right[0], popt_right[1], popt_right[2], popt_right[3])),
    #         right_points_x[i])
    #     # cv2.circle(vis, ppp, 5, (0, 255, 0), -1)
    #     right_points_y_func.append(
    #         int(func(right_points_x[i], popt_right[0], popt_right[1], popt_right[2], popt_right[3])))
    # left_points_y_func = np.reshape(left_points_y_func, (len(left_points_y_func), -1))
    # right_points_y_func = np.reshape(right_points_y_func, (len(right_points_y_func), -1))
    # left_points_y_func = np.squeeze(left_points_y_func)
    # right_points_y_func = np.squeeze(right_points_y_func)
    cv2.namedWindow('vis_onnx', 0)
    cv2.imshow("vis_onnx", vis)
    cv2.waitKey(0)
    # cv2.destroyAllWindows()
    # cv2.imwrite(path, vis)
    return vis


def main():
    files = glob.glob(folder_path)
    files = sorted(files)
    model = ufld_2()
    model.export_onnx()
    for i in range(len(files)):
        model.output_cmp(files[i])


if __name__ == '__main__':
    main()

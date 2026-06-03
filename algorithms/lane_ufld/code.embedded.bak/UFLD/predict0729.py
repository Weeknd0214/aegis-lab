import torch, os, cv2, glob
from model.model import parsingNet
from utils.common import merge_config
from utils.dist_utils import dist_print
# import torch
import scipy.special, tqdm
import numpy as np
import torchvision.transforms as transforms
from data.dataset import LaneTestDataset
from data.constant import culane_row_anchor, tusimple_row_anchor
from scipy.optimize import curve_fit
from lane_show import is_in_poly, handle_point, poly_fitting, draw_values
import time
import PIL
import re


class PredictLane:
    def __init__(self):
        # super(PredictLane, self).__init__()
        # self.img =img
        self.cls_num_per_lane = 56
        self.griding_num = 100
        self.backbone = '34'
        start_0 = time.time()
        self.net = parsingNet(pretrained=False, backbone=self.backbone, cls_dim=(self.griding_num + 1, self.cls_num_per_lane, 4),
                         # use_aux=False).to(device)
                         use_aux=False).cuda()  # we dont need auxiliary segmentation in testing

        state_dict = torch.load('./model/curb_c599.pth', map_location='cuda')['model']
        compatible_state_dict = {}
        for k, v in state_dict.items():
            if 'module.' in k:
                compatible_state_dict[k[7:]] = v
            else:
                compatible_state_dict[k] = v

        self.net.load_state_dict(compatible_state_dict, strict=False)
        self.net.eval()
        # net = torch.load(cfg.test_model, map_location='cuda')
        end_0 = time.time()
        count_0 = end_0 - start_0
        print('the load net time is : ', count_0)
        self.img_transforms = transforms.Compose([
            transforms.Resize((288, 800)),
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
        ])
        self.count = 0

    def predict(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.count += 1
        start_1 = time.time()
        img_i = PIL.Image.fromarray(img.astype(np.uint8))
        img_t = self.img_transforms(img_i)
        img_w, img_h = 1280, 720
        row_anchor = tusimple_row_anchor
        # print(img_t)
        img_t = img_t.reshape(1, 3, 288, 800)
        # print(img_t)
        # print(img_t.shape)
        imgs = img_t.cuda()
        end_1 = time.time()
        count_1 = end_1 - start_1
        print('the predeal time is : ', count_1)
        # imgs = imgs.to(device)
        with torch.no_grad():
            start_t = time.time()
            out = self.net(imgs)
            # print(out[0].shape)
            end_t = time.time()
            count_t = end_t - start_t
        print('the pre time is : ', count_t)
        col_sample = np.linspace(0, 800 - 1, self.griding_num)
        col_sample_w = col_sample[1] - col_sample[0]
        out_j = out[0].data.cpu().numpy()
        # print(out_j.shape, type(out_j))
        out_j = out_j[:, ::-1, :]
        prob = scipy.special.softmax(out_j[:-1, :, :], axis=0)
        idx = np.arange(self.griding_num) + 1
        idx = idx.reshape(-1, 1, 1)
        loc = np.sum(prob * idx, axis=0)
        out_j = np.argmax(out_j, axis=0)
        loc[out_j == self.griding_num] = 0
        out_j = loc
        vis = img
        lanes_list = []
        for i in range(out_j.shape[1]):
            # print(i)
            points_list = []
            # print(out_j.shape[1])
            if np.sum(out_j[:, i] != 0) > 2:
                # poly = [[400, 211], [23, 403], [930, 230], [1276, 442]]  # ROI区域
                poly = [[0, 0], [0, 720], [1280, 0], [1280, 720]]  # ROI区域
                lane_x = []
                lane_y = []
                for k in range(out_j.shape[0]):
                    # print(out_j.shape[0])6
                    if out_j[k, i] > 0:
                        ppp = (int(out_j[k, i] * col_sample_w * img_w / 800) - 1,
                               int(img_h * (row_anchor[self.cls_num_per_lane - 1 - k] / 288)) - 1)

                        is_in = is_in_poly(ppp, poly)
                        if is_in == True:
                            # 将处理后的点坐标添如一个空列表做拟合用
                            lane_x.append(ppp[0])
                            lane_y.append(ppp[1])
                            points_list.append((float(ppp[0]), float(ppp[1])))
                            cv2.circle(vis, ppp, 5, (0, 255, 0), -1)
                lx, ly, rx, ry = handle_point(lane_x, lane_y)
                # print('1111111111', lx, ly, rx, ry)
                # curvature, distance_from_center = poly_fitting(lx, ly, rx, ry)
                # draw_values(vis, curvature, distance_from_center)
                # print(points_list)
                # lane = np.uint8()
            if points_list != []:
                lanes_list.append(points_list)
        cv2.imshow('vis', vis)
        cv2.waitKey(1)
        return lanes_list


if __name__ == "__main__":
    torch.backends.cudnn.benchmark = True
    # args, cfg = merge_config()
    data_root = r'C:\data\curb_data\curb_data\2'
    dist_print('start testing...')
    backbone = '34'
    # jpg_file = 'n_9\\frame6000.jpg'
    pic_list = glob.glob(data_root + '/*.png')
    pattern_number_oeder = '(\d*?).png'
    pic_list.sort(key=lambda x: int(re.findall(pattern_number_oeder, x)[0]))
    a = PredictLane()
    # print(pic_list)
    for pic in pic_list:
        print(pic)
        img = cv2.imread(pic)
        lanes_list = a.predict(img)

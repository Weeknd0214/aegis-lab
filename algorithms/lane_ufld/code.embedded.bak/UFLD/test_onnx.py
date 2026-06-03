import torch, os, cv2
from model.model import parsingNet
from utils.common import merge_config
from utils.dist_utils import dist_print
import torch
import scipy.special, tqdm
import numpy as np
import torchvision.transforms as transforms
from data.dataset import LaneTestDataset
from data.constant import culane_row_anchor, tusimple_row_anchor
from scipy.optimize import curve_fit
from lane_show import is_in_poly, handle_point, poly_fitting, draw_values
import time
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# 自定义函数 e指数形式
def func(x, a, b, c):
    return a * np.sqrt(x) * (b * np.square(x) + c)


def get_curve_fit(x, y):
    # 非线性最小二乘法拟合
    popt, pcov = curve_fit(func, x, y)
    # 获取popt里面是拟合系数
    # print(popt)
    a = popt[0]
    b = popt[1]
    c = popt[2]
    yvals = func(x, a, b, c)  # 拟合y值
    # print('popt:', popt)
    # print('系数a:', a)
    # print('系数b:', b)
    # print('系数c:', c)
    # print('系数pcov:', pcov)
    # print('系数yvals:', yvals)
    return yvals


if __name__ == "__main__":
    torch.backends.cudnn.benchmark = True

    args, cfg = merge_config()

    dist_print('start testing...')
    from model.backbone import SUPPORTED_BACKBONES
    assert cfg.backbone in SUPPORTED_BACKBONES

    if cfg.dataset == 'CULane':
        cls_num_per_lane = 18
    elif cfg.dataset == 'Tusimple':
        cls_num_per_lane = 56
    else:
        raise NotImplementedError

    # blob = cv.dnn.blobFromImage(img_t, scalefactor=1.0, swapRB=True, crop=False)  # 将image转化为 1x3x64x64 格式输入模型中
    net = cv2.dnn.readNetFromONNX("./model/tusimple_18.onnx")
    # model = onnx.load('./model/tusimple_18.onnx')
    # net.setInput(blob)

    img_transforms = transforms.Compose([
        transforms.Resize((288, 800)),
        transforms.ToTensor(),
        transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ])
    if cfg.dataset == 'CULane':
        splits = ['test0_normal.txt']
        # splits = ['test0_normal.txt', 'test1_crowd.txt', 'test2_hlight.txt', 'test3_shadow.txt', 'test4_noline.txt', 'test5_arrow.txt', 'test6_curve.txt', 'test7_cross.txt', 'test8_night.txt']
        datasets = [LaneTestDataset(cfg.data_root, os.path.join(cfg.data_root, 'list/test_split/' + split),
                                    img_transform=img_transforms) for split in splits]
        img_w, img_h = 1280, 720
        # img_w, img_h = 1640, 590
        row_anchor = culane_row_anchor
    elif cfg.dataset == 'Tusimple':
        splits = ['test4.txt']
        datasets = [LaneTestDataset(cfg.data_root, os.path.join(cfg.data_root, split), img_transform=img_transforms) for
                    split in splits]
        # img_w, img_h = 998, 560
        # img_w, img_h = 960, 546
        img_w, img_h = 1280, 720
        row_anchor = tusimple_row_anchor
    else:
        raise NotImplementedError
    for split, dataset in zip(splits, datasets):
        loader = torch.utils.data.DataLoader(dataset, batch_size=1, shuffle=False, num_workers=1)
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        print(split[:-3] + 'avi')
        vout = cv2.VideoWriter(split[:-3] + 'avi', fourcc, 15.0, (img_w, img_h))
        for i, data in enumerate(tqdm.tqdm(loader)):
            imgs, names = data
            print(imgs.shape, names)
            imgs = imgs.cuda()
            print(type(imgs))
            # imgs = imgs.to(device)
            with torch.no_grad():
                start_t = time.time()
                imgs = imgs.numpy()
                blob = cv2.dnn.blobFromImage(imgs, scalefactor=1.0, swapRB=False, crop=False)
                net.setInput(blob)
                out = net(imgs)
                end_t = time.time()
                count_t = end_t - start_t
                print('the pre time is : ', count_t)
            col_sample = np.linspace(0, 800 - 1, cfg.griding_num)
            col_sample_w = col_sample[1] - col_sample[0]
            out_j = out[0].data.cpu().numpy()
            out_j = out_j[:, ::-1, :]
            prob = scipy.special.softmax(out_j[:-1, :, :], axis=0)
            idx = np.arange(cfg.griding_num) + 1
            idx = idx.reshape(-1, 1, 1)
            loc = np.sum(prob * idx, axis=0)
            out_j = np.argmax(out_j, axis=0)
            loc[out_j == cfg.griding_num] = 0
            out_j = loc
            print('out:', len(out_j), out_j.shape)
            x_list = []
            y_list = []
            # import pdb; pdb.set_trace()
            vis = cv2.imread(os.path.join(cfg.data_root, names[0]))
            for i in range(out_j.shape[1]):
                # print(out_j.shape[1])
                if np.sum(out_j[:, i] != 0) > 2:
                    poly = [[50, 50], [50, 719], [1250, 50], [1250, 719]]  # ROI区域
                    lane_x = []
                    lane_y = []
                    for k in range(out_j.shape[0]):
                        # print(out_j.shape[0])
                        if out_j[k, i] > 0:
                            ppp = (int(out_j[k, i] * col_sample_w * img_w / 800) - 1,
                                   int(img_h * (row_anchor[cls_num_per_lane - 1 - k] / 288)) - 1)

                            is_in = is_in_poly(ppp, poly)
                            if is_in == True:
                                # 将处理后的点坐标添如一个空列表做拟合用
                                lane_x.append(ppp[0])
                                lane_y.append(ppp[1])
                                cv2.circle(vis, ppp, 5, (0, 255, 0), -1)
                    lx, ly, rx, ry = handle_point(lane_x, lane_y)
                    # print(lx, ly, rx, ry)
                    curvature, distance_from_center = poly_fitting(lx, ly, rx, ry)
                    draw_values(vis, curvature, distance_from_center)
            cv2.imshow('vis', vis)
            cv2.waitKey(1)
            vout.write(vis)

        vout.release()

#!/usr/bin/env python3
"""Compare PyTorch vs ONNX UFLD inference with identical post-process and visualization."""

import argparse
import os

import cv2
import numpy as np
import onnxruntime as ort
import scipy.special
import torch
import torchvision.transforms as transforms
from PIL import Image

from data.constant import tusimple_row_anchor
from model.model import parsingNet
from utils.common import checkpoint_state_dict


def decode_lanes(out, griding_num, cls_num_per_lane, img_w, img_h, row_anchor):
    """Shared post-process (demo_new.py logic). out: (101, 56, 4) numpy."""
    col_sample = np.linspace(0, 800 - 1, griding_num)
    col_sample_w = col_sample[1] - col_sample[0]

    out_j = out[:, ::-1, :]
    prob = scipy.special.softmax(out_j[:-1, :, :], axis=0)
    idx = np.arange(griding_num) + 1
    idx = idx.reshape(-1, 1, 1)
    loc = np.sum(prob * idx, axis=0)
    out_j = np.argmax(out_j, axis=0)
    loc[out_j == griding_num] = 0
    out_j = loc

    lanes = []
    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255)]
    for lane_i in range(out_j.shape[1]):
        pts = []
        if np.sum(out_j[:, lane_i] != 0) <= 2:
            continue
        for k in range(out_j.shape[0]):
            if out_j[k, lane_i] > 0:
                x = int(out_j[k, lane_i] * col_sample_w * img_w / 800) - 1
                y = int(img_h * (row_anchor[cls_num_per_lane - 1 - k] / 288)) - 1
                pts.append((x, y))
        lanes.append((pts, colors[lane_i % len(colors)]))
    return lanes


def draw_lanes(vis, lanes, radius=5):
    for pts, color in lanes:
        for p in pts:
            cv2.circle(vis, p, radius, color, -1)
    return vis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pth', default='log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.pth')
    ap.add_argument('--onnx', default='log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.onnx')
    ap.add_argument('--image', required=True)
    ap.add_argument('--out_dir', default='log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/vis_compare')
    ap.add_argument('--griding_num', type=int, default=100)
    ap.add_argument('--num_lanes', type=int, default=4)
    ap.add_argument('--backbone', default='18')
    ap.add_argument('--img_w', type=int, default=1280)
    ap.add_argument('--img_h', type=int, default=720)
    args = ap.parse_args()

    cls_num_per_lane = 56
    row_anchor = tusimple_row_anchor

    tf = transforms.Compose([
        transforms.Resize((288, 800)),
        transforms.ToTensor(),
        transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ])
    tensor = tf(Image.open(args.image).convert('RGB')).unsqueeze(0)

    net = parsingNet(
        pretrained=False,
        backbone=args.backbone,
        cls_dim=(args.griding_num + 1, cls_num_per_lane, args.num_lanes),
        use_aux=False,
    )
    net.load_state_dict(checkpoint_state_dict(args.pth, map_location='cpu'), strict=False)
    net.eval()
    with torch.no_grad():
        pt_out = net(tensor).numpy()[0]

    sess = ort.InferenceSession(args.onnx, providers=['CPUExecutionProvider'])
    onnx_out = sess.run(['output'], {'input': tensor.numpy()})[0][0]

    diff = np.abs(pt_out - onnx_out)
    print(f'output max diff: {diff.max():.6e}, mean diff: {diff.mean():.6e}')
    print(f'allclose: {np.allclose(pt_out, onnx_out, rtol=1e-3, atol=1e-4)}')

    vis_base = cv2.imread(args.image)
    if vis_base is None:
        raise FileNotFoundError(args.image)
    vis_base = cv2.resize(vis_base, (args.img_w, args.img_h))

    lanes_pt = decode_lanes(pt_out, args.griding_num, cls_num_per_lane, args.img_w, args.img_h, row_anchor)
    lanes_onnx = decode_lanes(onnx_out, args.griding_num, cls_num_per_lane, args.img_w, args.img_h, row_anchor)

    vis_pt = draw_lanes(vis_base.copy(), lanes_pt)
    vis_onnx = draw_lanes(vis_base.copy(), lanes_onnx)
    panel = np.hstack([vis_pt, vis_onnx])
    cv2.putText(panel, 'PyTorch', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    cv2.putText(panel, 'ONNX', (args.img_w + 20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

    # pixel diff on visualization (lane points only)
    pt_pts = {p for lane, _ in lanes_pt for p in lane}
    onnx_pts = {p for lane, _ in lanes_onnx for p in lane}
    print(f'lane points: pytorch={len(pt_pts)}, onnx={len(onnx_pts)}, only_pt={len(pt_pts-onnx_pts)}, only_onnx={len(onnx_pts-pt_pts)}')

    os.makedirs(args.out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.image))[0]
    out_panel = os.path.join(args.out_dir, f'{base}_pth_vs_onnx.jpg')
    out_pt = os.path.join(args.out_dir, f'{base}_pytorch.jpg')
    out_onnx = os.path.join(args.out_dir, f'{base}_onnx.jpg')
    cv2.imwrite(out_panel, panel)
    cv2.imwrite(out_pt, vis_pt)
    cv2.imwrite(out_onnx, vis_onnx)
    print('saved:', out_panel)
    print('saved:', out_pt)
    print('saved:', out_onnx)


if __name__ == '__main__':
    main()

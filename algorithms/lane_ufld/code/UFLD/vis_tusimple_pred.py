"""Visualize TuSimple-format predictions from test.py (tusimple_eval_tmp.0.txt)."""

import argparse
import json
import os

import cv2

LANE_COLORS = [(0, 255, 0), (0, 0, 255), (255, 0, 0), (0, 255, 255)]


def draw_lanes(img, lanes, h_samples):
    for lane_idx, xs in enumerate(lanes):
        color = LANE_COLORS[lane_idx % len(LANE_COLORS)]
        pts = [(int(x), int(y)) for x, y in zip(xs, h_samples) if x >= 0]
        for i in range(len(pts) - 1):
            cv2.line(img, pts[i], pts[i + 1], color, 3)
        for p in pts:
            cv2.circle(img, p, 4, color, -1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--pred',
        default='tmp/tusimple_eval_tmp.0.txt',
        help='prediction jsonl from test.py',
    )
    parser.add_argument(
        '--data_root',
        default='/home/chengfanglu/DATA/lane0_copy/DATASET',
        help='dataset root (images under data_root/raw_file)',
    )
    parser.add_argument(
        '--out_dir',
        default='tmp/vis_pred',
        help='directory to save overlay images',
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    n_ok = 0
    with open(args.pred, 'r') as f:
        for line in f:
            item = json.loads(line)
            rel = item['raw_file']
            img_path = os.path.join(args.data_root, rel)
            if not os.path.isfile(img_path):
                print('skip (missing):', img_path)
                continue
            img = cv2.imread(img_path)
            if img is None:
                print('skip (read failed):', img_path)
                continue
            draw_lanes(img, item['lanes'], item['h_samples'])
            out_path = os.path.join(args.out_dir, rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            cv2.imwrite(out_path, img)
            n_ok += 1
            print('saved', out_path)

    print(f'done: {n_ok} images -> {args.out_dir}')


if __name__ == '__main__':
    main()

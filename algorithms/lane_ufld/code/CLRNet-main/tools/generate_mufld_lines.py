#!/usr/bin/env python3
"""Pre-generate .lines.txt from masks for faster CLRNet training."""
import argparse
import os
import os.path as osp
import sys

import cv2
from tqdm import tqdm

ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
sys.path.insert(0, ROOT)

from clrnet.utils.mask_to_lanes import lanes_from_mask, lanes_to_lines_txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--list", required=True, help="train_gt.txt path")
    ap.add_argument("--sample-y", type=int, nargs="+", default=list(range(710, 150, -10)))
    ap.add_argument("--num-lanes", type=int, default=4)
    ap.add_argument("--cache-dir", default="cache/mufld_lines")
    args = ap.parse_args()

    list_path = args.list if osp.isabs(args.list) else osp.join(args.data_root, args.list)
    n_ok = 0
    with open(list_path) as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    for line in tqdm(lines):
        parts = line.split()
        if len(parts) < 2:
            continue
        img_rel, _ = parts[0].lstrip("/"), parts[1].lstrip("/")
        img_path = osp.join(args.data_root, img_rel)
        base = img_path[:-4]
        out = osp.join(args.data_root, args.cache_dir, osp.relpath(base, args.data_root) + ".lines.txt")
        mask_path = osp.join(args.data_root, parts[1].lstrip("/"))
        mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if mask is None:
            continue
        if mask.ndim > 2:
            mask = mask[:, :, 0]
        lanes = lanes_from_mask(mask, args.sample_y, args.num_lanes)
        os.makedirs(osp.dirname(out), exist_ok=True)
        with open(out, "w") as fp:
            fp.write(lanes_to_lines_txt(lanes))
        n_ok += 1
    print("wrote", n_ok, "lines files under", args.cache_dir)


if __name__ == "__main__":
    main()

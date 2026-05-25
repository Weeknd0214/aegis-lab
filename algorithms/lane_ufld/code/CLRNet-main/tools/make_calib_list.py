#!/usr/bin/env python3
"""Write a calibration image list for RKNN (one absolute path per line)."""

import argparse
import glob
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--glob', default='**/*.jpg', help='glob under --root')
    parser.add_argument('--root', default='.', help='search root')
    parser.add_argument('--out', default='models/calib_images.txt')
    parser.add_argument('--max', type=int, default=20)
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    paths = []
    for p in sorted(glob.glob(os.path.join(root, args.glob), recursive=True)):
        if os.path.isfile(p):
            paths.append(os.path.abspath(p))
        if len(paths) >= args.max:
            break

    if not paths:
        raise SystemExit(f'no images under {root} with {args.glob}')

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w') as f:
        f.write('\n'.join(paths) + '\n')
    print(f'wrote {len(paths)} paths -> {out}')


if __name__ == '__main__':
    main()

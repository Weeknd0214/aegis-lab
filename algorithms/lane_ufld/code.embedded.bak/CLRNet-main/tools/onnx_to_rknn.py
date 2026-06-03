#!/usr/bin/env python3
"""ONNX -> RKNN for CLRNet (platform rk3576). Requires rknn-toolkit2 on x86 Linux."""

import argparse
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--onnx', default='models/clrernet_culane_dla34.onnx')
    parser.add_argument('--rknn', default='models/clrernet_culane_dla34_rk3576.rknn')
    parser.add_argument('--platform', default='rk3576')
    parser.add_argument('--dtype', default='i8', choices=['i8', 'fp'])
    parser.add_argument('--dataset', default=None,
                        help='txt list of calibration images (one path per line)')
    parser.add_argument('--height', type=int, default=320)
    parser.add_argument('--width', type=int, default=800)
    args = parser.parse_args()

    try:
        from rknn.api import RKNN
    except ImportError as e:
        raise SystemExit(
            'Install rknn-toolkit2 in a separate env: pip install rknn-toolkit2\n' + str(e)
        ) from e

    if not args.dataset:
        raise SystemExit(
            'Provide --dataset with a txt of RGB image paths for INT8 calibration.'
        )

    rknn = RKNN(verbose=True)
    print('config:', args.platform, args.dtype)
    rknn.config(mean_values=[[103.939, 116.779, 123.68]],
                std_values=[[1, 1, 1]],
                target_platform=args.platform,
                quantized_dtype='asymmetric_quantized-8' if args.dtype == 'i8' else 'float16')

    ret = rknn.load_onnx(model=args.onnx)
    if ret != 0:
        raise SystemExit('load_onnx failed')

    ret = rknn.build(do_quantization=(args.dtype == 'i8'), dataset=args.dataset)
    if ret != 0:
        raise SystemExit('build failed')

    os.makedirs(os.path.dirname(args.rknn) or '.', exist_ok=True)
    ret = rknn.export_rknn(args.rknn)
    if ret != 0:
        raise SystemExit('export_rknn failed')
    print('saved:', os.path.abspath(args.rknn))
    rknn.release()


if __name__ == '__main__':
    main()

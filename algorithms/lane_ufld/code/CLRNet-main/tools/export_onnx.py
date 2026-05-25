#!/usr/bin/env python3
"""Export CLRNet to ONNX (bilinear_grid_sample, no GridSample)."""

import argparse
import os
import sys
import types

import numpy as np
import torch
import torch.nn as nn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)


def _stub_nms_cuda_ext():
    """Export does not need CUDA NMS; stub so clrnet.ops imports on CPU-only hosts."""
    if 'clrnet.ops.nms_impl' in sys.modules:
        return
    stub = types.ModuleType('clrnet.ops.nms_impl')

    def _nms_forward(boxes, scores, overlap, top_k):
        raise NotImplementedError('NMS runs on CPU after RKNN inference, not in exported graph')

    stub.nms_forward = _nms_forward
    sys.modules['clrnet.ops.nms_impl'] = stub


_stub_nms_cuda_ext()

from clrnet.utils.config import Config  # noqa: E402
from clrnet.models.registry import build_net  # noqa: E402


class CLRNetOnnxWrapper(nn.Module):
    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, img):
        # Detector returns (B, num_priors, 77) in eval mode
        return self.net({'img': img})


def _remap_clrernet_keys(key):
    """Map CLRerNet (mmdet) checkpoint keys to Turoad CLRNet-main module names."""
    key = key.replace('bbox_head.', 'heads.')
    key = key.replace('heads.sample_x_indices', 'heads.sample_x_indexs')
    key = key.replace('heads.anchor_generator.prior_embeddings',
                      'heads.prior_embeddings')
    key = key.replace('heads.attention.attention.', 'heads.roi_gather.')
    key = key.replace('heads.attention.', 'heads.roi_gather.')
    return key


def load_weights(net, path):
    ckpt = torch.load(path, map_location='cpu')
    if isinstance(ckpt, dict):
        if 'net' in ckpt:
            state = ckpt['net']
        elif 'state_dict' in ckpt:
            state = ckpt['state_dict']
        else:
            state = ckpt
    else:
        state = ckpt
    remapped = {_remap_clrernet_keys(k): v for k, v in state.items()}
    missing, unexpected = net.load_state_dict(remapped, strict=False)
    print('load_state_dict: missing', len(missing), 'unexpected', len(unexpected))
    if missing:
        print('  missing sample:', missing[:8])
    if unexpected:
        print('  unexpected sample:', unexpected[:8])


def compare_outputs(wrapper, dummy, onnx_path):
    try:
        import onnxruntime as ort
    except ImportError:
        print('onnxruntime not installed, skip numeric check')
        return

    wrapper.eval()
    with torch.no_grad():
        pt_out = wrapper(dummy).numpy()

    sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    ort_out = sess.run(None, {'img': dummy.numpy()})[0]
    diff = np.abs(pt_out - ort_out).max()
    print(f'PyTorch vs ONNX max diff: {diff:.6f}')
    print(f'output shape: {pt_out.shape}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='configs/clrnet/clr_dla34_culane.py')
    parser.add_argument('--checkpoint', default='models/clrernet_culane_dla34.pth')
    parser.add_argument('--output', default='models/clrernet_culane_dla34.onnx')
    parser.add_argument('--opset', type=int, default=11)
    parser.add_argument('--height', type=int, default=None)
    parser.add_argument('--width', type=int, default=None)
    parser.add_argument('--check', action='store_true', help='run onnxruntime compare')
    args = parser.parse_args()

    cfg = Config.fromfile(os.path.join(ROOT, args.config))
    h = args.height or cfg.img_h
    w = args.width or cfg.img_w

    # Avoid downloading ImageNet weights; we load the CLRNet checkpoint below.
    if cfg.get('backbone', None) is not None:
        cfg.backbone.pretrained = False

    net = build_net(cfg)
    load_weights(net, os.path.join(ROOT, args.checkpoint))
    net.eval()

    wrapper = CLRNetOnnxWrapper(net)
    dummy = torch.randn(1, 3, h, w)
    out_path = os.path.join(ROOT, args.output)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)

    print(f'export ONNX: {out_path}')
    print(f'input: (1, 3, {h}, {w})')
    with torch.no_grad():
        test_out = wrapper(dummy)
    print(f'output: {tuple(test_out.shape)}')

    torch.onnx.export(
        wrapper,
        dummy,
        out_path,
        opset_version=args.opset,
        input_names=['img'],
        output_names=['predictions'],
        dynamic_axes={'img': {0: 'batch'}, 'predictions': {0: 'batch'}},
        do_constant_folding=True,
    )
    print('saved:', out_path)

    try:
        import onnx
        model = onnx.load(out_path)
        ops = {n.op_type for n in model.graph.node}
        print('GridSample in graph:', 'GridSample' in ops)
        print('node op types (sample):', sorted(ops)[:20], '...')
    except ImportError:
        pass

    if args.check:
        compare_outputs(wrapper, dummy, out_path)


if __name__ == '__main__':
    main()

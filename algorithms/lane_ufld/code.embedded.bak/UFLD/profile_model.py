"""Count parameters and FLOPs for a UFLD parsingNet checkpoint."""

import argparse
import os
import re

import torch

from model.backbone import is_vovnet
from model.model import parsingNet
from utils.common import checkpoint_state_dict
from utils.config import Config

# TuSimple / lane0 UFLD row anchors (fixed in original repo)
CLS_NUM_PER_LANE = 56
INPUT_SIZE = (288, 800)


def parse_cfg_txt(cfg_path):
    """Parse saved cfg.txt from train.py (Config repr line)."""
    with open(cfg_path, encoding='utf-8') as f:
        text = f.read()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f'cannot parse dict from {cfg_path}')
    # cfg.txt uses single-quoted python dict repr
    return eval(m.group())


def build_net(backbone, griding_num, num_lanes, use_aux, pretrained=False):
    return parsingNet(
        pretrained=pretrained,
        backbone=str(backbone),
        cls_dim=(griding_num + 1, CLS_NUM_PER_LANE, num_lanes),
        use_aux=use_aux,
    )


def count_params(net):
    total = sum(p.numel() for p in net.parameters())
    trainable = sum(p.numel() for p in net.parameters() if p.requires_grad)
    return total, trainable


def count_flops(net, input_size):
    x = torch.randn(1, 3, *input_size)
    from torch.utils.flop_counter import FlopCounterMode

    with FlopCounterMode(display=False) as fc:
        with torch.no_grad():
            net(x)
    total = fc.get_total_flops()
    breakdown = fc.get_flop_counts().get('Global', {})
    return total, breakdown, tuple(net(x).shape)


def main():
    parser = argparse.ArgumentParser(description='UFLD params / FLOPs profiler')
    parser.add_argument(
        '--run_dir',
        default='log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18',
        help='training log dir containing cfg.txt and optional best.pth',
    )
    parser.add_argument('--config', default=None, help='config .py (overrides cfg.txt)')
    parser.add_argument('--model_path', default=None, help='.pth checkpoint (optional)')
    parser.add_argument('--backbone', default=None)
    parser.add_argument('--griding_num', type=int, default=None)
    parser.add_argument('--num_lanes', type=int, default=None)
    parser.add_argument('--use_aux', action='store_true', default=None)
    parser.add_argument('--height', type=int, default=INPUT_SIZE[0])
    parser.add_argument('--width', type=int, default=INPUT_SIZE[1])
    args = parser.parse_args()

    backbone = '18'
    griding_num = 100
    num_lanes = 4
    use_aux = False
    model_path = args.model_path

    if args.config:
        cfg = Config.fromfile(args.config)
        backbone = cfg.backbone
        griding_num = cfg.griding_num
        num_lanes = cfg.num_lanes
        use_aux = getattr(cfg, 'use_aux', False)
        if model_path is None and getattr(cfg, 'test_model', None):
            model_path = cfg.test_model
    elif args.run_dir and os.path.isfile(os.path.join(args.run_dir, 'cfg.txt')):
        cfg = parse_cfg_txt(os.path.join(args.run_dir, 'cfg.txt'))
        backbone = cfg.get('backbone', backbone)
        griding_num = cfg.get('griding_num', griding_num)
        num_lanes = cfg.get('num_lanes', num_lanes)
        use_aux = cfg.get('use_aux', use_aux)
        if model_path is None:
            for name in ('best.pth', 'latest.pth', 'model.pt'):
                p = os.path.join(args.run_dir, name)
                if os.path.isfile(p):
                    model_path = p
                    break

    if args.backbone is not None:
        backbone = args.backbone
    if args.griding_num is not None:
        griding_num = args.griding_num
    if args.num_lanes is not None:
        num_lanes = args.num_lanes
    if args.use_aux is not None:
        use_aux = args.use_aux

    input_size = (args.height, args.width)
    net = build_net(backbone, griding_num, num_lanes, use_aux, pretrained=False)
    if model_path and os.path.isfile(model_path):
        net.load_state_dict(checkpoint_state_dict(model_path, map_location='cpu'), strict=False)
    net.eval()

    total, trainable = count_params(net)
    flops, breakdown, out_shape = count_flops(net, input_size)

    print('=== UFLD model profile ===')
    if model_path:
        print('checkpoint:', os.path.abspath(model_path))
    if args.run_dir:
        print('run_dir:', os.path.abspath(args.run_dir))
    arch = f'VoVNet({backbone})' if is_vovnet(backbone) else f'ResNet{backbone}'
    print(
        f'arch: {arch}, griding_num={griding_num}, num_lanes={num_lanes}, '
        f'use_aux={use_aux}, input=1x3x{input_size[0]}x{input_size[1]}'
    )
    print(f'output shape: {out_shape}')
    print(f'Parameters: {total:,}  ({total / 1e6:.4f} M)')
    print(f'Trainable:  {trainable:,}')
    print(f'FLOPs (PyTorch FlopCounterMode, 1 image): {flops:,}  ({flops / 1e9:.4f} GFLOPs)')
    print('FLOPs breakdown (top ops):')
    for op, v in sorted(breakdown.items(), key=lambda kv: -kv[1])[:6]:
        print(f'  {op}: {v / 1e9:.4f} G')


if __name__ == '__main__':
    main()

"""Export UFLD .pth checkpoint to ONNX (matches tusimple_res18_4lane_v1 / best.pth)."""

import argparse
import os

import torch

from model.model import parsingNet
from utils.common import checkpoint_state_dict
from utils.config import Config


def export_onnx(
    model_path,
    output_path=None,
    backbone='18',
    griding_num=100,
    num_lanes=4,
    opset=11,
):
    if output_path is None:
        base, _ = os.path.splitext(model_path)
        output_path = base + '.onnx'

    cls_num_per_lane = 56  # TuSimple row anchors
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    net = parsingNet(
        pretrained=False,
        backbone=backbone,
        cls_dim=(griding_num + 1, cls_num_per_lane, num_lanes),
        use_aux=False,
    ).to(device)
    net.load_state_dict(checkpoint_state_dict(model_path, map_location=device), strict=False)
    net.eval()

    dummy = torch.randn(1, 3, 288, 800, device=device)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    torch.onnx.export(
        net,
        dummy,
        output_path,
        opset_version=opset,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}},
        dynamo=False,  # legacy exporter embeds weights (PyTorch 2.9+ default may omit)
    )
    print('saved:', os.path.abspath(output_path))
    print('input:  [1, 3, 288, 800]')
    print('output:', tuple(net(dummy).shape))
    return output_path


def main():
    default_pth = 'log/20250702_165153_lr_1e-05_b_32_ufld_2lanes_res18/best.pth'
    parser = argparse.ArgumentParser(description='Export UFLD checkpoint to ONNX')
    parser.add_argument('--config', default=None, help='optional py config (overrides defaults)')
    parser.add_argument('--model_path', default=default_pth, help='path to .pth')
    parser.add_argument('--output', default=None, help='output .onnx path')
    parser.add_argument('--backbone', default=None)
    parser.add_argument('--griding_num', type=int, default=None)
    parser.add_argument('--num_lanes', type=int, default=None)
    parser.add_argument('--opset', type=int, default=11)
    args = parser.parse_args()

    backbone = '18'
    griding_num = 100
    num_lanes = 4
    model_path = args.model_path
    output = args.output

    if args.config:
        cfg = Config.fromfile(args.config)
        backbone = cfg.backbone
        griding_num = cfg.griding_num
        num_lanes = cfg.num_lanes
        if getattr(cfg, 'test_model', None):
            model_path = cfg.test_model

    if args.backbone is not None:
        backbone = args.backbone
    if args.griding_num is not None:
        griding_num = args.griding_num
    if args.num_lanes is not None:
        num_lanes = args.num_lanes

    export_onnx(
        model_path,
        output_path=output,
        backbone=backbone,
        griding_num=griding_num,
        num_lanes=num_lanes,
        opset=args.opset,
    )


if __name__ == '__main__':
    main()

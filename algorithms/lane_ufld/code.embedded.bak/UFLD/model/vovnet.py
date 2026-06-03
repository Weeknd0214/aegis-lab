# VoVNet backbone (OSA + eSE), adapted from vovnet-detectron2 (no detectron2 dependency).
# Reference: BK2/archive/vovnet-detectron2-master/vovnet/vovnet.py

from collections import OrderedDict

import torch
import torch.nn as nn
import torch.nn.functional as F

VoVNet19_slim_dw_eSE = {
    'stem': [64, 64, 64],
    'stage_conv_ch': [64, 80, 96, 112],
    'stage_out_ch': [112, 256, 384, 512],
    'layer_per_block': 3,
    'block_per_stage': [1, 1, 1, 1],
    'eSE': True,
    'dw': True,
}

VoVNet19_dw_eSE = {
    'stem': [64, 64, 64],
    'stage_conv_ch': [128, 160, 192, 224],
    'stage_out_ch': [256, 512, 768, 1024],
    'layer_per_block': 3,
    'block_per_stage': [1, 1, 1, 1],
    'eSE': True,
    'dw': True,
}

VoVNet19_slim_eSE = {
    'stem': [64, 64, 128],
    'stage_conv_ch': [64, 80, 96, 112],
    'stage_out_ch': [112, 256, 384, 512],
    'layer_per_block': 3,
    'block_per_stage': [1, 1, 1, 1],
    'eSE': True,
    'dw': False,
}

VoVNet19_eSE = {
    'stem': [64, 64, 128],
    'stage_conv_ch': [128, 160, 192, 224],
    'stage_out_ch': [256, 512, 768, 1024],
    'layer_per_block': 3,
    'block_per_stage': [1, 1, 1, 1],
    'eSE': True,
    'dw': False,
}

VoVNet39_eSE = {
    'stem': [64, 64, 128],
    'stage_conv_ch': [128, 160, 192, 224],
    'stage_out_ch': [256, 512, 768, 1024],
    'layer_per_block': 5,
    'block_per_stage': [1, 1, 2, 2],
    'eSE': True,
    'dw': False,
}

VoVNet57_eSE = {
    'stem': [64, 64, 128],
    'stage_conv_ch': [128, 160, 192, 224],
    'stage_out_ch': [256, 512, 768, 1024],
    'layer_per_block': 5,
    'block_per_stage': [1, 1, 4, 3],
    'eSE': True,
    'dw': False,
}

VoVNet99_eSE = {
    'stem': [64, 64, 128],
    'stage_conv_ch': [128, 160, 192, 224],
    'stage_out_ch': [256, 512, 768, 1024],
    'layer_per_block': 5,
    'block_per_stage': [1, 3, 9, 3],
    'eSE': True,
    'dw': False,
}

STAGE_SPECS = {
    'V-19-slim-dw-eSE': VoVNet19_slim_dw_eSE,
    'V-19-dw-eSE': VoVNet19_dw_eSE,
    'V-19-slim-eSE': VoVNet19_slim_eSE,
    'V-19-eSE': VoVNet19_eSE,
    'V-39-eSE': VoVNet39_eSE,
    'V-57-eSE': VoVNet57_eSE,
    'V-99-eSE': VoVNet99_eSE,
}

# Short names used in UFLD configs (backbone='vov19slim', ...)
VOVNET_ALIASES = {
    'vov19slim_dw': 'V-19-slim-dw-eSE',
    'vov19_dw': 'V-19-dw-eSE',
    'vov19slim': 'V-19-slim-eSE',
    'vov19': 'V-19-eSE',
    'vov39': 'V-39-eSE',
    'vov57': 'V-57-eSE',
    'vov99': 'V-99-eSE',
}


def _bn(ch):
    return nn.BatchNorm2d(ch)


def dw_conv3x3(in_channels, out_channels, module_name, postfix, stride=1, kernel_size=3, padding=1):
    return [
        (f'{module_name}_{postfix}/dw', nn.Conv2d(
            in_channels, out_channels, kernel_size=kernel_size, stride=stride,
            padding=padding, groups=out_channels, bias=False)),
        (f'{module_name}_{postfix}/pw', nn.Conv2d(
            in_channels, out_channels, kernel_size=1, stride=1, padding=0, bias=False)),
        (f'{module_name}_{postfix}/bn', _bn(out_channels)),
        (f'{module_name}_{postfix}/relu', nn.ReLU(inplace=True)),
    ]


def conv3x3(in_channels, out_channels, module_name, postfix, stride=1, groups=1,
            kernel_size=3, padding=1):
    return [
        (f'{module_name}_{postfix}/conv', nn.Conv2d(
            in_channels, out_channels, kernel_size=kernel_size, stride=stride,
            padding=padding, groups=groups, bias=False)),
        (f'{module_name}_{postfix}/bn', _bn(out_channels)),
        (f'{module_name}_{postfix}/relu', nn.ReLU(inplace=True)),
    ]


def conv1x1(in_channels, out_channels, module_name, postfix, stride=1, groups=1,
            kernel_size=1, padding=0):
    return [
        (f'{module_name}_{postfix}/conv', nn.Conv2d(
            in_channels, out_channels, kernel_size=kernel_size, stride=stride,
            padding=padding, groups=groups, bias=False)),
        (f'{module_name}_{postfix}/bn', _bn(out_channels)),
        (f'{module_name}_{postfix}/relu', nn.ReLU(inplace=True)),
    ]


class Hsigmoid(nn.Module):
    def __init__(self, inplace=True):
        super().__init__()
        self.inplace = inplace

    def forward(self, x):
        return F.relu6(x + 3.0, inplace=self.inplace) / 6.0


class eSEModule(nn.Module):
    def __init__(self, channel):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Conv2d(channel, channel, kernel_size=1, padding=0)
        self.hsigmoid = Hsigmoid()

    def forward(self, x):
        return x * self.hsigmoid(self.fc(self.avg_pool(x)))


class _OSA_module(nn.Module):
    def __init__(self, in_ch, stage_ch, concat_ch, layer_per_block, module_name,
                 identity=False, depthwise=False):
        super().__init__()
        self.identity = identity
        self.depthwise = depthwise
        self.is_reduced = False
        self.layers = nn.ModuleList()
        in_channel = in_ch
        if self.depthwise and in_channel != stage_ch:
            self.is_reduced = True
            self.conv_reduction = nn.Sequential(
                OrderedDict(conv1x1(in_channel, stage_ch, f'{module_name}_reduction', '0')))
        for i in range(layer_per_block):
            if self.depthwise:
                self.layers.append(nn.Sequential(OrderedDict(
                    dw_conv3x3(stage_ch, stage_ch, module_name, str(i)))))
            else:
                self.layers.append(nn.Sequential(OrderedDict(
                    conv3x3(in_channel, stage_ch, module_name, str(i)))))
            in_channel = stage_ch

        in_channel = in_ch + layer_per_block * stage_ch
        self.concat = nn.Sequential(OrderedDict(
            conv1x1(in_channel, concat_ch, module_name, 'concat')))
        self.ese = eSEModule(concat_ch)

    def forward(self, x):
        identity_feat = x
        output = [x]
        if self.depthwise and self.is_reduced:
            x = self.conv_reduction(x)
        for layer in self.layers:
            x = layer(x)
            output.append(x)
        x = torch.cat(output, dim=1)
        xt = self.ese(self.concat(x))
        if self.identity:
            xt = xt + identity_feat
        return xt


class _OSA_stage(nn.Sequential):
    def __init__(self, in_ch, stage_ch, concat_ch, block_per_stage, layer_per_block,
                 stage_num, depthwise=False):
        super().__init__()
        if stage_num != 2:
            self.add_module('Pooling', nn.MaxPool2d(kernel_size=3, stride=2, ceil_mode=True))
        module_name = f'OSA{stage_num}_1'
        self.add_module(module_name, _OSA_module(
            in_ch, stage_ch, concat_ch, layer_per_block, module_name, depthwise=depthwise))
        for i in range(block_per_stage - 1):
            module_name = f'OSA{stage_num}_{i + 2}'
            self.add_module(module_name, _OSA_module(
                concat_ch, stage_ch, concat_ch, layer_per_block, module_name,
                identity=True, depthwise=depthwise))


class VoVNetBody(nn.Module):
    """VoVNet stages; forward returns (stage3, stage4, stage5) at strides 8/16/32."""

    def __init__(self, variant='V-19-slim-eSE', input_ch=3):
        super().__init__()
        if variant in VOVNET_ALIASES:
            variant = VOVNET_ALIASES[variant]
        if variant not in STAGE_SPECS:
            raise KeyError(f'Unknown VoVNet variant {variant!r}, choose from {list(STAGE_SPECS)}')
        self.variant = variant
        spec = STAGE_SPECS[variant]

        stem_ch = spec['stem']
        config_stage_ch = spec['stage_conv_ch']
        config_concat_ch = spec['stage_out_ch']
        block_per_stage = spec['block_per_stage']
        layer_per_block = spec['layer_per_block']
        depthwise = spec['dw']

        conv_type = dw_conv3x3 if depthwise else conv3x3
        stem = conv3x3(input_ch, stem_ch[0], 'stem', '1', stride=2)
        stem += conv_type(stem_ch[0], stem_ch[1], 'stem', '2', stride=1)
        stem += conv_type(stem_ch[1], stem_ch[2], 'stem', '3', stride=2)
        self.stem = nn.Sequential(OrderedDict(stem))

        in_ch_list = [stem_ch[2]] + config_concat_ch[:-1]
        self.stage2 = _OSA_stage(
            in_ch_list[0], config_stage_ch[0], config_concat_ch[0],
            block_per_stage[0], layer_per_block, 2, depthwise=depthwise)
        self.stage3 = _OSA_stage(
            in_ch_list[1], config_stage_ch[1], config_concat_ch[1],
            block_per_stage[1], layer_per_block, 3, depthwise=depthwise)
        self.stage4 = _OSA_stage(
            in_ch_list[2], config_stage_ch[2], config_concat_ch[2],
            block_per_stage[2], layer_per_block, 4, depthwise=depthwise)
        self.stage5 = _OSA_stage(
            in_ch_list[3], config_stage_ch[3], config_concat_ch[3],
            block_per_stage[3], layer_per_block, 5, depthwise=depthwise)

        self.out_channels = {
            'c3': config_concat_ch[1],
            'c4': config_concat_ch[2],
            'c5': config_concat_ch[3],
        }
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)

    def forward(self, x):
        x = self.stem(x)
        x = self.stage2(x)
        c3 = self.stage3(x)
        c4 = self.stage4(c3)
        c5 = self.stage5(c4)
        return c3, c4, c5


class vovnet(nn.Module):
    """UFLD-compatible wrapper (same interface as resnet: x2, x3, x4)."""

    def __init__(self, variant='vov19slim', pretrained=False):
        super().__init__()
        if pretrained:
            import warnings
            warnings.warn(
                'VoVNet has no torchvision pretrained weights in UFLD; '
                'train from scratch or load a custom checkpoint.',
                UserWarning,
                stacklevel=2,
            )
        key = variant if variant in VOVNET_ALIASES else variant
        self.body = VoVNetBody(key)
        self.variant = self.body.variant

    def forward(self, x):
        return self.body(x)

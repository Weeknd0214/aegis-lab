import torch
import torch.nn.modules
import torchvision

from model.vovnet import VOVNET_ALIASES, STAGE_SPECS

RESNET_BACKBONES = ['18', '34', '50', '101', '152', '50next', '101next', '50wide', '101wide']
VOVMNET_BACKBONES = list(VOVNET_ALIASES.keys())
SUPPORTED_BACKBONES = RESNET_BACKBONES + VOVMNET_BACKBONES + ['vgg']


def is_vovnet(backbone):
    return str(backbone) in VOVNET_ALIASES


def get_backbone_spec(backbone):
    """Channel layout for parsingNet pool / aux heads."""
    backbone = str(backbone)
    if is_vovnet(backbone):
        from model.vovnet import VOVNET_ALIASES as _aliases
        variant = _aliases[backbone]
        ch = STAGE_SPECS[variant]['stage_out_ch']
        return {
            'pool_in': ch[3],
            'aux': (ch[1], ch[2], ch[3]),
            'family': 'vov',
        }
    if backbone in ['18', '34']:
        return {'pool_in': 512, 'aux': (128, 256, 512), 'family': 'resnet'}
    if backbone == 'vgg':
        return {'pool_in': 512, 'aux': (128, 256, 512), 'family': 'vgg'}
    return {'pool_in': 2048, 'aux': (512, 1024, 2048), 'family': 'resnet'}


def build_backbone(backbone, pretrained=False):
    backbone = str(backbone)
    if is_vovnet(backbone):
        from model.vovnet import vovnet
        return vovnet(backbone, pretrained=pretrained)
    if backbone == 'vgg':
        return vgg16bn(pretrained=pretrained)
    return resnet(backbone, pretrained=pretrained)


class vgg16bn(torch.nn.Module):
    def __init__(self, pretrained=False):
        super(vgg16bn, self).__init__()
        model = list(torchvision.models.vgg16_bn(pretrained=pretrained).features.children())
        model = model[:33] + model[34:43]
        self.model = torch.nn.Sequential(*model)

    def forward(self, x):
        return self.model(x)


class resnet(torch.nn.Module):
    def __init__(self, layers, pretrained=False):
        super(resnet, self).__init__()
        if layers == '18':
            model = torchvision.models.resnet18(pretrained=pretrained)
        elif layers == '34':
            model = torchvision.models.resnet34(pretrained=pretrained)
        elif layers == '50':
            model = torchvision.models.resnet50(pretrained=pretrained)
        elif layers == '101':
            model = torchvision.models.resnet101(pretrained=pretrained)
        elif layers == '152':
            model = torchvision.models.resnet152(pretrained=pretrained)
        elif layers == '50next':
            model = torchvision.models.resnext50_32x4d(pretrained=pretrained)
        elif layers == '101next':
            model = torchvision.models.resnext101_32x8d(pretrained=pretrained)
        elif layers == '50wide':
            model = torchvision.models.wide_resnet50_2(pretrained=pretrained)
        elif layers == '101wide':
            model = torchvision.models.wide_resnet101_2(pretrained=pretrained)
        else:
            raise NotImplementedError(f'Unknown ResNet backbone: {layers}')

        self.conv1 = model.conv1
        self.bn1 = model.bn1
        self.relu = model.relu
        self.maxpool = model.maxpool
        self.layer1 = model.layer1
        self.layer2 = model.layer2
        self.layer3 = model.layer3
        self.layer4 = model.layer4

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)
        x = self.layer1(x)
        x2 = self.layer2(x)
        x3 = self.layer3(x2)
        x4 = self.layer4(x3)
        return x2, x3, x4

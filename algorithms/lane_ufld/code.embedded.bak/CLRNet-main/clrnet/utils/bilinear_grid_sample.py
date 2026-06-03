# Bilinear grid_sample using Pad + Gather (ONNX/RKNN friendly).
# Ref: https://zenn.dev/pinto0309/scraps/7d4032067d0160
#      https://github.com/ibaiGorordo/CREStereo-Pytorch/.../nets/utils/utils.py

import torch
import torch.nn.functional as F


def bilinear_grid_sample(im, grid, align_corners=False):
    """Drop-in replacement for F.grid_sample(..., mode='bilinear', padding_zeros).

    Args:
        im: (N, C, H, W)
        grid: (N, Hg, Wg, 2), x/y in [-1, 1] (same as grid_sample)
    """
    n, c, h, w = im.shape
    gn, gh, gw, _ = grid.shape
    assert n == gn

    x = grid[..., 0]
    y = grid[..., 1]

    if align_corners:
        x = ((x + 1) / 2) * (w - 1)
        y = ((y + 1) / 2) * (h - 1)
    else:
        x = ((x + 1) * w - 1) / 2
        y = ((y + 1) * h - 1) / 2

    x = x.reshape(n, -1)
    y = y.reshape(n, -1)

    x0 = torch.floor(x).long()
    y0 = torch.floor(y).long()
    x1 = x0 + 1
    y1 = y0 + 1

    wa = ((x1 - x) * (y1 - y)).unsqueeze(1)
    wb = ((x1 - x) * (y - y0)).unsqueeze(1)
    wc = ((x - x0) * (y1 - y)).unsqueeze(1)
    wd = ((x - x0) * (y - y0)).unsqueeze(1)

    im_padded = F.pad(im, pad=[1, 1, 1, 1], mode='constant', value=0)
    padded_h = h + 2
    padded_w = w + 2
    x0, x1, y0, y1 = x0 + 1, x1 + 1, y0 + 1, y1 + 1

    # Clip in float so ONNX exports valid Clip (ORT rejects int64 Clip bounds).
    x0 = x0.float().clamp(0, padded_w - 1).long()
    x1 = x1.float().clamp(0, padded_w - 1).long()
    y0 = y0.float().clamp(0, padded_h - 1).long()
    y1 = y1.float().clamp(0, padded_h - 1).long()

    im_flat = im_padded.reshape(n, c, -1)

    x0_y0 = (x0 + y0 * padded_w).unsqueeze(1).expand(-1, c, -1)
    x0_y1 = (x0 + y1 * padded_w).unsqueeze(1).expand(-1, c, -1)
    x1_y0 = (x1 + y0 * padded_w).unsqueeze(1).expand(-1, c, -1)
    x1_y1 = (x1 + y1 * padded_w).unsqueeze(1).expand(-1, c, -1)

    ia = torch.gather(im_flat, 2, x0_y0)
    ib = torch.gather(im_flat, 2, x0_y1)
    ic = torch.gather(im_flat, 2, x1_y0)
    id_ = torch.gather(im_flat, 2, x1_y1)

    out = ia * wa + ib * wb + ic * wc + id_ * wd
    return out.reshape(n, c, gh, gw)

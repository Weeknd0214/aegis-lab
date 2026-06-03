import os
import torch
from model.model import parsingNet
from utils.common import merge_config, checkpoint_state_dict
from utils.dist_utils import dist_print
from evaluation.eval_wrapper import eval_lane

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
if __name__ == "__main__":
    torch.backends.cudnn.benchmark = True

    args, cfg = merge_config()

    distributed = False
    if 'WORLD_SIZE' in os.environ:
        distributed = int(os.environ['WORLD_SIZE']) > 1

    if distributed:
        torch.cuda.set_device(args.local_rank)
        torch.distributed.init_process_group(backend='nccl', init_method='env://')
    dist_print('start testing...')
    from model.backbone import SUPPORTED_BACKBONES
    assert cfg.backbone in SUPPORTED_BACKBONES

    if cfg.dataset == 'CULane':
        cls_num_per_lane = 18
    elif cfg.dataset == 'Tusimple':
        cls_num_per_lane = 56
    else:
        raise NotImplementedError

    net = parsingNet(pretrained=False, backbone=cfg.backbone, cls_dim=(cfg.griding_num+1, cls_num_per_lane,
                                                                       cfg.num_lanes), use_aux=False).to(device)
                                                                       # cfg.num_lanes), use_aux=False).cuda()
    # we don't need auxiliary segmentation in testing

    net.load_state_dict(checkpoint_state_dict(cfg.test_model, map_location=device), strict=False)

    if distributed:
        net = torch.nn.parallel.DistributedDataParallel(net, device_ids=[args.local_rank])

    if not os.path.exists(cfg.test_work_dir):
        os.mkdir(cfg.test_work_dir)

    test_list = getattr(cfg, 'test_list', None)
    skip_eval = getattr(cfg, 'skip_eval', False)
    eval_lane(net, cfg.dataset, cfg.data_root, cfg.test_work_dir, cfg.griding_num, False, distributed,
              test_list=test_list, skip_eval=skip_eval)
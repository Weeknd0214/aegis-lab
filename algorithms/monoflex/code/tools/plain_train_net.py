import torch
import logging
import pdb
import os
import datetime
import warnings
warnings.filterwarnings("ignore")

from config import cfg
from data import make_data_loader
from solver import build_optimizer, build_scheduler

from tqdm import tqdm
from utils.check_point import DetectronCheckpointer
from engine import (
    default_argument_parser,
    default_setup,
    launch,
)
from utils import comm
from utils.backup_files import sync_root

from engine.trainer import do_train
from engine.test_net import run_test

from model.detector import KeypointDetector
from model.detector import KeypointDetector2
from data import build_test_loader
import resource

# torch.multiprocessing.set_sharing_strategy('file_system')

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
print("rlimit: ", rlimit)
resource.setrlimit(resource.RLIMIT_NOFILE, (4096, rlimit[1]))

torch.backends.cudnn.enabled = True # enable cudnn and uncertainty imported
# torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = True # enable cudnn to search the best algorithm

def train(cfg, model, device, distributed):
    data_loader = make_data_loader(cfg, is_train=True)
    data_loaders_val = build_test_loader(cfg, is_train=False)

    total_iters_each_epoch = len(data_loader.dataset) // cfg.SOLVER.IMS_PER_BATCH
    # use epoch rather than iterations for saving checkpoint and validation
    if cfg.SOLVER.EVAL_AND_SAVE_EPOCH:
        cfg.SOLVER.MAX_ITERATION = cfg.SOLVER.MAX_EPOCHS * total_iters_each_epoch
        cfg.SOLVER.SAVE_CHECKPOINT_INTERVAL = total_iters_each_epoch * cfg.SOLVER.SAVE_CHECKPOINT_EPOCH_INTERVAL
        cfg.SOLVER.EVAL_INTERVAL = total_iters_each_epoch * cfg.SOLVER.EVAL_EPOCH_INTERVAL
        cfg.SOLVER.STEPS = [total_iters_each_epoch * x for x in cfg.SOLVER.DECAY_EPOCH_STEPS]
        cfg.SOLVER.WARMUP_STEPS = cfg.SOLVER.WARMUP_EPOCH * total_iters_each_epoch
    
    cfg.freeze()

    optimizer = build_optimizer(model, cfg)
    scheduler, warmup_scheduler = build_scheduler(
        optimizer, total_iters_each_epoch=total_iters_each_epoch, 
        optim_cfg=cfg.SOLVER,
    )

    arguments = {}
    arguments["iteration"] = 0
    arguments["iter_per_epoch"] = total_iters_each_epoch

    output_dir = cfg.OUTPUT_DIR
    save_to_disk = comm.get_rank() == 0

    checkpointer = DetectronCheckpointer(
        cfg, model, optimizer, scheduler, output_dir, save_to_disk
    )

    if len(cfg.MODEL.WEIGHT) > 0:
        extra_checkpoint_data = checkpointer.load(cfg.MODEL.WEIGHT, use_latest=False)
        arguments.update(extra_checkpoint_data)

    do_train(
        cfg,
        distributed,
        model,
        data_loader,
        data_loaders_val,
        optimizer,
        scheduler,
        warmup_scheduler,
        checkpointer,
        device,
        arguments,
    )

def setup(args):
    cfg.merge_from_file(args.config_file)
    cfg.merge_from_list(args.opts)
    
    cfg.SOLVER.IMS_PER_BATCH = args.batch_size
    cfg.DATALOADER.NUM_WORKERS = args.num_work
    cfg.TEST.EVAL_DIS_IOUS = args.eval_iou
    cfg.TEST.EVAL_DEPTH = args.eval_depth 
    
    if args.vis_thre > 0:
        cfg.TEST.VISUALIZE_THRESHOLD = args.vis_thre 
    
    if args.output is not None:
        cfg.OUTPUT_DIR = args.output

    if args.test:
        cfg.DATASETS.TEST_SPLIT = 'test'
        cfg.DATASETS.TEST = ("kitti_test",)

    cfg.START_TIME = datetime.datetime.strftime(datetime.datetime.now(), '%m-%d %H:%M:%S')
    default_setup(cfg, args)

    return cfg

def main(args):
    cfg = setup(args)

    distributed = comm.get_world_size() > 1
    if not distributed: cfg.MODEL.USE_SYNC_BN = False

    if args.export_onnx:
        model = KeypointDetector2(cfg)
    else:
        model = KeypointDetector(cfg)
    device = torch.device(cfg.MODEL.DEVICE)
    model.to(device)

    if args.eval_only:
        checkpointer = DetectronCheckpointer(
            cfg, model, save_dir=cfg.OUTPUT_DIR
        )
        ckpt = cfg.MODEL.WEIGHT if args.ckpt is None else args.ckpt
        _ = checkpointer.load(ckpt, use_latest=args.ckpt is None)

        # 从engine/inference.py的compute_on_dataset中部分移过来
        if args.export_onnx:
            data_loaders_val = build_test_loader(cfg)
            checkpointer.model.eval()
            with torch.no_grad():
                # dummy_input = torch.randn(1, 3, cfg.INPUT.HEIGHT_TEST, cfg.INPUT.WIDTH_TEST).to(device)
                # print("dummy_input.shape = ", dummy_input.shape)
                for idx, batch in enumerate(tqdm(data_loaders_val)):
                    images, targets, image_ids = batch["images"], batch["targets"], batch["img_ids"]
                    images = images.to(device)
                    images = images.tensors
                    print("images.shape = ", images.shape)

                    # extract label data for visualize
                    # vis_target = targets[0]
                    targets = [target.to(device) for target in targets]
                    # edge_indices = torch.stack([t.get_field("edge_indices") for t in targets]) # B x K x 2
                    # edge_lens = torch.stack([t.get_field("edge_len") for t in targets]) # B
                    # print("edge_indices.shape = ", edge_indices.shape)
                    # torch.set_printoptions(profile="full")
                    # print("edge_indices = ", edge_indices)
                    # torch.set_printoptions(profile="default")
                    # print("edge_lens = ", edge_lens)
                    torch.onnx.export(checkpointer.model, images, "monoflex_pytorch_no_ABN_no_EDGE_FUSION.onnx", verbose=True)
                    torch.cuda.synchronize()
                    return

        return run_test(cfg, checkpointer.model, vis=args.vis, eval_score_iou=args.eval_score_iou, eval_all_depths=args.eval_all_depths)

    if distributed:
        # convert BN to SyncBN
        if cfg.MODEL.USE_SYNC_BN:
            model = torch.nn.SyncBatchNorm.convert_sync_batchnorm(model)

        model = torch.nn.parallel.DistributedDataParallel(
            model, device_ids=[comm.get_local_rank()], broadcast_buffers=False,
            find_unused_parameters=True,
        )

    train(cfg, model, device, distributed)

if __name__ == '__main__':
    args = default_argument_parser().parse_args()
    
    print("Command Line Args:", args)

    # backup all python files when training
    if not args.eval_only and args.output is not None:
        sync_root('.', os.path.join(args.output, 'backup'))
        import shutil
        shutil.copy2(args.config_file, os.path.join(args.output, 'backup', os.path.basename(args.config_file)))

        print("Finish backup all files")

    launch(
        main,
        args.num_gpus,
        num_machines=args.num_machines,
        machine_rank=args.machine_rank,
        dist_url=args.dist_url,
        args=(args,),
    )

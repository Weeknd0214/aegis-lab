import os, argparse
from utils.dist_utils import is_main_process, dist_print, DistSummaryWriter
from utils.config import Config
import torch
import time

def load_checkpoint(path, map_location='cpu'):
    """Load legacy UFLD checkpoints (may contain DataParallel); PyTorch 2.6+ needs weights_only=False."""
    return torch.load(path, map_location=map_location, weights_only=False)


def checkpoint_state_dict(path, map_location='cpu'):
    """Return state_dict from a .pth file (handles DataParallel module or raw state_dict)."""
    ckpt = load_checkpoint(path, map_location=map_location)
    model = ckpt['model'] if isinstance(ckpt, dict) and 'model' in ckpt else ckpt
    if isinstance(model, torch.nn.Module):
        model = model.state_dict()
    compatible = {}
    for k, v in model.items():
        if 'module.' in k:
            compatible[k[7:]] = v
        else:
            compatible[k] = v
    return compatible


def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', help = 'path to config file')
    parser.add_argument('--local_rank', type=int, default=0)

    parser.add_argument('--dataset', default = None, type = str)
    parser.add_argument('--data_root', default = None, type = str)
    parser.add_argument('--epoch', default = None, type = int)
    parser.add_argument('--batch_size', default = None, type = int)
    parser.add_argument('--optimizer', default = None, type = str)
    parser.add_argument('--learning_rate', default = None, type = float)
    parser.add_argument('--weight_decay', default = None, type = float)
    parser.add_argument('--momentum', default = None, type = float)
    parser.add_argument('--scheduler', default = None, type = str)
    parser.add_argument('--steps', default = None, type = int, nargs='+')
    parser.add_argument('--gamma', default = None, type = float)
    parser.add_argument('--warmup', default = None, type = str)
    parser.add_argument('--warmup_iters', default = None, type = int)
    parser.add_argument('--backbone', default = None, type = str)
    parser.add_argument('--griding_num', default = None, type = int)
    parser.add_argument('--use_aux', default = None, type = str2bool)
    parser.add_argument('--sim_loss_w', default = None, type = float)
    parser.add_argument('--shp_loss_w', default = None, type = float)
    parser.add_argument('--note', default = None, type = str)
    parser.add_argument('--log_path', default = None, type = str)
    parser.add_argument('--finetune', default = None, type = str)
    parser.add_argument('--resume', default = None, type = str)
    parser.add_argument('--test_model', default = None, type = str)
    parser.add_argument('--test_work_dir', default = None, type = str)
    parser.add_argument('--num_lanes', default = None, type = int)
    parser.add_argument('--test_list', default = None, type = str,
                        help='relative path under data_root, e.g. list/test.txt')
    parser.add_argument('--skip_eval', default = None, type = str2bool,
                        help='only run inference, skip metric evaluation')
    parser.add_argument('--auto_backup', action='store_true', help='automatically backup current code in the log path')

    return parser

def merge_config():
    args = get_args().parse_args()
    cfg = Config.fromfile(args.config)

    items = ['dataset','data_root','epoch','batch_size','optimizer','learning_rate',
    'weight_decay','momentum','scheduler','steps','gamma','warmup','warmup_iters',
    'use_aux','griding_num','backbone','sim_loss_w','shp_loss_w','note','log_path',
    'finetune','resume', 'test_model','test_work_dir', 'num_lanes', 'test_list', 'skip_eval']
    for item in items:
        if getattr(args, item) is not None:
            dist_print('merge ', item, ' config')
            setattr(cfg, item, getattr(args, item))
    return args, cfg


def save_model(net, optimizer, epoch, save_path, distributed):
    if is_main_process():
        # model_state_dict = net.state_dict()
        # state = {'model': model_state_dict, 'optimizer': optimizer.state_dict()}
        # # state = {'model': net, 'optimizer': optimizer}
        # assert os.path.exists(save_path)
        # #model_path = os.path.join(save_path, 'ep%03d.pth' % epoch)
        # model_path = os.path.join(save_path, 'best.pth')
        # torch.save(state, model_path)
        model_state_all = net
        state = {'model': model_state_all, 'optimizer': optimizer.state_dict(),'epoch':epoch}
        assert os.path.exists(save_path)
        model_path = os.path.join(save_path, 'best.pth')
        torch.save(state, model_path)

def save_model_pruned_model(model, optimizer, epoch, save_path, distributed):
    state = {'model': model.state_dict(), 'optimizer': optimizer.state_dict(),'epoch':epoch}
    assert os.path.exists(save_path)
    model_path = os.path.join(save_path, 'pruned_model.pth')
    torch.save(state, model_path)

def save_model_fine_tune(net, optimizer, epoch, save_path, distributed):
    if is_main_process():
        # model_state_dict = net.state_dict()
        # state = {'model': model_state_dict, 'optimizer': optimizer.state_dict()}
        # # state = {'model': net, 'optimizer': optimizer}
        # assert os.path.exists(save_path)
        # #model_path = os.path.join(save_path, 'ep%03d.pth' % epoch)
        # model_path = os.path.join(save_path, 'best.pth')
        # torch.save(state, model_path)
        model_state_dict = net.state_dict() ##注意此处
        state = {'model': model_state_dict, 'optimizer': optimizer.state_dict(),'epoch':epoch}
        assert os.path.exists(save_path)
        model_path = os.path.join(save_path, 'fine_tune_model.pth')
        torch.save(state, model_path)

import pathspec


def cp_projects(auto_backup, to_path):
    if is_main_process() and auto_backup:
        with open('./.gitignore','r') as fp:
            ign = fp.read()
        ign += '\n.git'
        spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ign.splitlines())
        all_files = {os.path.join(root,name) for root,dirs,files in os.walk('./') for name in files}
        matches = spec.match_files(all_files)
        matches = set(matches)
        to_cp_files = all_files - matches
        dist_print('Copying projects to '+ to_path + ' for backup')
        t0 = time.time()
        warning_flag = True
        for f in to_cp_files:
            dirs = os.path.join(to_path,'code',os.path.split(f[2:])[0])
            if not os.path.exists(dirs):
                os.makedirs(dirs)
            os.system('cp %s %s'%(f,os.path.join(to_path,'code',f[2:])))
            elapsed_time = time.time() - t0
            if elapsed_time > 5 and warning_flag:
                dist_print('If the program is stuck, it might be copying large files in this directory. please don\'t set --auto_backup. Or please make you working directory clean, i.e, don\'t place large files like dataset, log results under this directory.')
                warning_flag = False


import datetime,os


def get_work_dir(cfg):
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    hyper_param_str = '_lr_%1.0e_b_%d' % (cfg.learning_rate, cfg.batch_size)
    log_path = cfg.log_path or './log'
    print(log_path, now + hyper_param_str + cfg.note)
    work_dir = os.path.join(log_path, now + hyper_param_str + cfg.note)
    return work_dir


def get_logger(work_dir, cfg):
    logger = DistSummaryWriter(work_dir)
    config_txt = os.path.join(work_dir, 'cfg.txt')
    if is_main_process():
        with open(config_txt, 'w') as fp:
            fp.write(str(cfg))

    return logger

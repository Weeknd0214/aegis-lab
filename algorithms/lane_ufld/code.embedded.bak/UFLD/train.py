import os
if "CUDA_VISIBLE_DEVICES" not in os.environ:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
import torch, datetime
import numpy as np

from model.model import parsingNet
from data.dataloader import get_train_loader

from utils.dist_utils import dist_print, dist_tqdm, is_main_process, DistSummaryWriter
from utils.factory import get_metric_dict, get_loss_dict, get_optimizer, get_scheduler
from utils.metrics import MultiLabelAcc, AccTopk, Metric_mIoU, update_metrics, reset_metrics

from utils.common import merge_config, save_model, cp_projects, load_checkpoint, checkpoint_state_dict
from utils.common import get_work_dir, get_logger
from utils.dataset_packs import resolve_train_list

import time
#from prun_model import *

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
top1_list=[]
top1_max=0
torch.cuda.is_available()
print(torch.cuda.is_available())
def inference(net, data_label, use_aux):
    if use_aux:
        img, cls_label, seg_label = data_label
        img = img.to(device)
        cls_label = cls_label.long().to(device)
        seg_label = seg_label.long().to(device)
        cls_out, seg_out = net(img)
        return {'cls_out': cls_out, 'cls_label': cls_label, 'seg_out':seg_out, 'seg_label': seg_label}
    else:
        img, cls_label = data_label
        img = img.to(device)
        cls_label = cls_label.long().to(device)
        cls_out = net(img)
        return {'cls_out': cls_out, 'cls_label': cls_label}


def resolve_val_data(results, use_aux):
    results['cls_out'] = torch.argmax(results['cls_out'], dim=1)
    if use_aux:
        results['seg_out'] = torch.argmax(results['seg_out'], dim=1)
    return results


def calc_loss(loss_dict, results, logger, global_step):
    loss = 0

    for i in range(len(loss_dict['name'])):

        data_src = loss_dict['data_src'][i]

        datas = [results[src] for src in data_src]

        loss_cur = loss_dict['op'][i](*datas)

        if global_step % 20 == 0:
            logger.add_scalar('loss/'+loss_dict['name'][i], loss_cur, global_step)

        loss += loss_cur * loss_dict['weight'][i]
    return loss


def train(net, data_loader, loss_dict, optimizer, scheduler,logger, epoch, metric_dict, use_aux):
    net.train()
    progress_bar = dist_tqdm(train_loader)
    t_data_0 = time.time()
    for b_idx, data_label in enumerate(progress_bar):
        # print(b_idx, len(data_label))
        t_data_1 = time.time()
        reset_metrics(metric_dict)
        global_step = epoch * len(data_loader) + b_idx

        t_net_0 = time.time()
        results = inference(net, data_label, use_aux)

        loss = calc_loss(loss_dict, results, logger, global_step)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        scheduler.step(global_step)
        t_net_1 = time.time()

        results = resolve_val_data(results, use_aux)

        update_metrics(metric_dict, results)
        if global_step % 20 == 0:
            for me_name, me_op in zip(metric_dict['name'], metric_dict['op']):
                logger.add_scalar('metric/' + me_name, me_op.get(), global_step=global_step)
        logger.add_scalar('meta/lr', optimizer.param_groups[0]['lr'], global_step=global_step)

        if hasattr(progress_bar, 'set_postfix'):
            for me_name, me_op in zip(metric_dict['name'], metric_dict['op']):
                if (me_name == 'top1' and b_idx==progress_bar.total-1):
                    top1_list.append(me_op.get())
            kwargs = {me_name: '%.3f' % me_op.get() for me_name, me_op in zip(metric_dict['name'], metric_dict['op'])}
            progress_bar.set_postfix(loss = '%.3f' % float(loss),
                                    data_time = '%.3f' % float(t_data_1 - t_data_0), 
                                    net_time = '%.3f' % float(t_net_1 - t_net_0), 
                                    **kwargs)
        t_data_0 = time.time()
        

if __name__ == "__main__":
    torch.backends.cudnn.benchmark = True

    args, cfg = merge_config()

    work_dir = get_work_dir(cfg)

    distributed = False
    # distributed = True
    if 'WORLD_SIZE' in os.environ:
        distributed = int(os.environ['WORLD_SIZE']) > 1

    if distributed:
        if not torch.cuda.is_available():
            raise RuntimeError("Distributed training requires CUDA")
        torch.cuda.set_device(args.local_rank)
        torch.distributed.init_process_group(backend='nccl', init_method='env://')
    dist_print(datetime.datetime.now().strftime('[%Y/%m/%d %H:%M:%S]') + ' start training...')
    dist_print(cfg)
    from model.backbone import SUPPORTED_BACKBONES
    assert cfg.backbone in SUPPORTED_BACKBONES, f'backbone must be one of {SUPPORTED_BACKBONES}'

    train_list = resolve_train_list(cfg)
    dist_print("train_list:", train_list)
    num_workers = int(os.environ.get("UFLD_NUM_WORKERS", "4" if device.type == "cuda" else "0"))
    train_loader, cls_num_per_lane = get_train_loader(
        cfg.batch_size, cfg.data_root, cfg.griding_num, cfg.dataset, cfg.use_aux,
        distributed, cfg.num_lanes, train_list=train_list, num_workers=num_workers,
    )
    net = parsingNet(
        pretrained=True, backbone=cfg.backbone,
        cls_dim=(cfg.griding_num + 1, cls_num_per_lane, cfg.num_lanes), use_aux=cfg.use_aux,
    ).to(device)
    if device.type == "cuda" and torch.cuda.device_count() > 1 and not distributed:
        print("Let's use", torch.cuda.device_count(), "GPUs!")
        net = torch.nn.DataParallel(net)
    
    
    
    #
    # net = parsingNet(pretrained=True, backbone=cfg.backbone,
    #                  cls_dim=(cfg.griding_num + 1, cls_num_per_lane, cfg.num_lanes), use_aux=cfg.use_aux).to(device)
    if distributed:
        net = torch.nn.parallel.DistributedDataParallel(net, device_ids=[args.local_rank])
    optimizer = get_optimizer(net, cfg)

    if cfg.finetune is not None:
        dist_print('finetune from ', cfg.finetune)
        state_all = checkpoint_state_dict(cfg.finetune)
        state_clip = {}  # only use backbone parameters
        for k, v in state_all.items():
            if 'model' in k:
                state_clip[k] = v
        net.load_state_dict(state_clip, strict=False)
    if cfg.resume is not None:
        dist_print('==> Resume model from ' + cfg.resume)
        resume_dict = load_checkpoint(cfg.resume, map_location='cpu')
        model = resume_dict['model']
        if isinstance(model, torch.nn.Module):
            net.load_state_dict(model.state_dict(), strict=False)
        else:
            net.load_state_dict(model, strict=False)
        if 'optimizer' in resume_dict.keys():
            optimizer.load_state_dict(resume_dict['optimizer'])
        resume_epoch = int(os.path.split(cfg.resume)[1][2:5]) + 1
    else:
        resume_epoch = 0

    scheduler = get_scheduler(optimizer, cfg, len(train_loader))
    dist_print(len(train_loader))
    metric_dict = get_metric_dict(cfg)
    loss_dict = get_loss_dict(cfg)
    logger = get_logger(work_dir, cfg)
    cp_projects(args.auto_backup, work_dir)
    file = open(work_dir + '/precision_record.txt', 'w')
    for epoch in range(resume_epoch, cfg.epoch):

        train(net, train_loader, loss_dict, optimizer, scheduler, logger, epoch, metric_dict, cfg.use_aux)
        # if epoch % 2==0:
        #if epoch > 0:
        #print('save the ', epoch, 'model')
        #save_model(net, optimizer, epoch, work_dir, distributed)


        if(epoch==0):
            top1_max=top1_list[-1]
            save_model(net, optimizer, epoch, work_dir, distributed)
            print('epcoh=0 and save best pth, the epoch: ', epoch, 'done')
        if(epoch!=0 and top1_list[-1]>top1_max):
            print('top1_list[-1]: ', top1_list[-1])
            print('top1_max: ', top1_max)
            save_model(net, optimizer, epoch, work_dir, distributed)
            print('save best pth, the epoch: ', epoch, 'done')

            file.write('top1_list[-1]: '+ str(top1_list[-1])+"\n")
            file.write('top1_max: ' + str(top1_max) + "\n")

            top1_max = top1_list[-1]
        else:
            save_model(net, optimizer, epoch, work_dir, distributed)
            print('donnot need to save best pth, the epoch: ', epoch, 'done')

    file.close()
    logger.close()


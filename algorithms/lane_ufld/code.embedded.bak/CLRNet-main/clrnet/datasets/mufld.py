import os
import os.path as osp
import pickle as pkl

import cv2
import numpy as np

from .base_dataset import BaseDataset
from .registry import DATASETS
from clrnet.utils.mask_to_lanes import lanes_from_mask, normalize_mask_labels
from clrnet.utils.dataset_packs import resolve_list_file

DEFAULT_LIST = {
    "train": "list/train_gt.txt",
    "val": "list/val_gt.txt",
    "test": "list/test_gt.txt",
}


@DATASETS.register_module
class MufldLane(BaseDataset):
    """
    MUFLD / lane0_copy DATASET packs.
    list: <img_rel> <mask_rel> per line; lanes from mask or cached .lines.txt
    """

    def __init__(
        self,
        data_root,
        split,
        processes=None,
        cfg=None,
        list_file=None,
    ):
        super().__init__(data_root, split, processes=processes, cfg=cfg)
        self.split = split
        if list_file is None:
            list_file = getattr(cfg, f"{split}_list_file", None)
        if list_file is None:
            list_file = resolve_list_file(cfg, split)
        if list_file is None:
            rel = DEFAULT_LIST.get(split, DEFAULT_LIST["train"])
            packs = getattr(cfg, "train_packs" if split == "train" else "val_packs", None)
            if packs:
                pack = packs[0] if isinstance(packs, (list, tuple)) else packs
                list_file = f"{pack}/{rel}"
            else:
                list_file = rel
        if osp.isabs(list_file):
            self.list_path = list_file
        else:
            self.list_path = osp.join(data_root, list_file)
        self.sample_ys = list(getattr(cfg, "sample_y", range(710, 150, -10)))
        self.num_lanes = getattr(cfg, "max_lanes", 4)
        self.lines_cache = getattr(cfg, "lines_cache_dir", "cache/mufld_lines")
        self.load_annotations()

    def load_annotations(self):
        self.logger.info("Loading MufldLane annotations from %s", self.list_path)
        os.makedirs("cache", exist_ok=True)
        cache_key = self.list_path.replace("/", "_")
        cache_path = osp.join("cache", f"mufld_{self.split}_{cache_key}.pkl")
        if osp.exists(cache_path):
            with open(cache_path, "rb") as f:
                self.data_infos = pkl.load(f)
            self.max_lanes = max(len(a["lanes"]) for a in self.data_infos) if self.data_infos else self.num_lanes
            return

        self.data_infos = []
        with open(self.list_path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 2:
                    continue
                info = self.load_annotation(parts)
                if info and len(info.get("lanes", [])) > 0:
                    self.data_infos.append(info)

        with open(cache_path, "wb") as f:
            pkl.dump(self.data_infos, f)
        self.max_lanes = max(len(a["lanes"]) for a in self.data_infos) if self.data_infos else self.num_lanes
        self.logger.info("Loaded %d samples, max_lanes=%d", len(self.data_infos), self.max_lanes)

    def _lines_path(self, img_path: str) -> str:
        base = img_path[:-4] if img_path.lower().endswith((".jpg", ".png")) else img_path
        cache_root = osp.join(self.data_root, self.lines_cache)
        rel = osp.relpath(base, self.data_root)
        return osp.join(cache_root, rel + ".lines.txt")

    def load_annotation(self, line):
        img_line = line[0].lstrip("/")
        mask_line = line[1].lstrip("/")
        img_path = osp.join(self.data_root, img_line)
        mask_path = osp.join(self.data_root, mask_line)
        infos = {
            "img_name": img_line,
            "img_path": img_path,
            "mask_path": mask_path,
        }
        if len(line) > 2:
            infos["lane_exist"] = np.array([int(x) for x in line[2:]])

        lines_path = self._lines_path(img_path)
        if osp.isfile(lines_path):
            with open(lines_path) as f:
                data = [list(map(float, ln.split())) for ln in f.readlines() if ln.strip()]
            lanes = [
                [(lane[i], lane[i + 1]) for i in range(0, len(lane), 2) if lane[i] >= 0 and lane[i + 1] >= 0]
                for lane in data
            ]
        elif osp.isfile(mask_path):
            mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
            if mask is None:
                return None
            if mask.ndim > 2:
                mask = mask[:, :, 0]
            lanes = lanes_from_mask(mask, self.sample_ys, self.num_lanes)
            if getattr(self.cfg, "write_lines_cache", False):
                os.makedirs(osp.dirname(lines_path), exist_ok=True)
                with open(lines_path, "w") as out:
                    for lane in lanes:
                        out.write(" ".join(f"{x:.5f} {y:.5f}" for x, y in lane) + "\n")
        else:
            return None

        lanes = [lane for lane in lanes if len(lane) > 2]
        lanes = [sorted(lane, key=lambda x: x[1]) for lane in lanes]
        infos["lanes"] = lanes
        return infos

    def __getitem__(self, idx):
        data_info = self.data_infos[idx]
        img = cv2.imread(data_info["img_path"])
        if img is None:
            raise FileNotFoundError(data_info["img_path"])
        img = img[self.cfg.cut_height :, :, :]
        sample = data_info.copy()
        sample.update({"img": img})

        if self.training:
            label = cv2.imread(sample["mask_path"], cv2.IMREAD_UNCHANGED)
            if label is None:
                raise FileNotFoundError(sample["mask_path"])
            if label.ndim > 2:
                label = label[:, :, 0]
            label = normalize_mask_labels(label.squeeze(), self.num_lanes)
            label = label[self.cfg.cut_height :, :]
            sample.update({"mask": label})

            if self.cfg.cut_height != 0:
                new_lanes = []
                for lane in sample["lanes"]:
                    new_lanes.append([(p[0], p[1] - self.cfg.cut_height) for p in lane])
                sample.update({"lanes": new_lanes})

        from mmcv.parallel import DataContainer as DC
        from clrnet.datasets.process import Process

        sample = self.processes(sample)
        meta = {"full_img_path": data_info["img_path"], "img_name": data_info["img_name"]}
        sample.update({"meta": DC(meta, cpu_only=True)})
        return sample

    def get_prediction_string(self, pred):
        ys = np.array(self.sample_ys) / self.cfg.ori_img_h
        out = []
        for lane in pred:
            xs = lane(ys)
            valid = (xs >= 0) & (xs < 1)
            xs = xs[valid] * self.cfg.ori_img_w
            lane_ys = ys[valid] * self.cfg.ori_img_h
            xs, lane_ys = xs[::-1], lane_ys[::-1]
            s = " ".join(f"{x:.5f} {y:.5f}" for x, y in zip(xs, lane_ys))
            if s:
                out.append(s)
        return "\n".join(out)

    def evaluate(self, predictions, output_basedir):
        os.makedirs(output_basedir, exist_ok=True)
        for idx, pred in enumerate(predictions):
            rel = self.data_infos[idx]["img_name"]
            out_dir = osp.join(output_basedir, osp.dirname(rel))
            os.makedirs(out_dir, exist_ok=True)
            out_file = osp.join(out_dir, osp.basename(rel)[:-4] + ".lines.txt")
            with open(out_file, "w") as f:
                f.write(self.get_prediction_string(pred))
        self.logger.info("Wrote predictions under %s (MUFLD: no CULane official eval)", output_basedir)
        return 0.0

export const LabelingStates: Record<
  string,
  { label: string; badge: string; hint: string }
> = {
  raw_pool: { label: "原图池", badge: "badge-pending", hint: "仅有图像，待送标或等待标注回传" },
  out_for_labeling: { label: "送标中", badge: "badge-training", hint: "已导出清单，等待标注方回传" },
  returned: { label: "回传待入库", badge: "badge-staged", hint: "数据已落盘，可执行 build / add" },
  ingested: { label: "已入库", badge: "badge-evaluated", hint: "已完成 ingest 或建包" },
};

export function forStage(stage: string) {
  return LabelingStates[stage] ?? { label: stage, badge: "badge-idle", hint: "" };
}

export const DropPaths = {
  dms_inbox: (ws: string, task: string, batch: string) =>
    `${ws}/datasets/dms/inbox/${task}/${batch}/`,
  dms_sources: (ws: string, pack: string, task: string, batch: string) =>
    `${ws}/datasets/dms/packs/${pack}/${task}/sources/${batch}/`,
  lane_add: (ws: string) => `${ws}/datasets/lane/  # archive 含 train_val_gt.txt`,
};

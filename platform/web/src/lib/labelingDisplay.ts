import type { LabelingBatchRow } from "./types";

/** ADAS 3D MOON：project=adas, task=cuboid_7cls */
export function isAdas3dScope(b: LabelingBatchRow): boolean {
  const project = b.project || "dms";
  const task = b.task || "";
  return project === "adas" && task === "cuboid_7cls";
}

/** ADAS 2D 七类：project=adas, task=det_7cls（兼容旧 dms+adas） */
export function isAdas2dScope(b: LabelingBatchRow): boolean {
  const project = b.project || "dms";
  const task = b.task || "";
  if (project === "adas" && task === "det_7cls") return true;
  return project === "dms" && task === "adas";
}

/** 前向 ADAS 相关（2D 七类、3D、交通标志 forward） */
export function isAdasScope(b: LabelingBatchRow): boolean {
  if (isAdas3dScope(b) || isAdas2dScope(b)) return true;
  const project = b.project || "dms";
  if (project === "lane") return false;
  const task = b.task || "";
  return b.domain === "forward" || task === "forward";
}

/** 列表「项目」列：DMS / ADAS / 车道线 */
export function displayProject(b: LabelingBatchRow): string {
  const project = b.project || "dms";
  if (project === "lane") return "车道线";
  if (isAdasScope(b)) return "ADAS";
  return "DMS";
}

export function displayProjectFields(row: {
  project?: string;
  task?: string;
  domain?: string;
}): string {
  return displayProject(row as LabelingBatchRow);
}

export function displayTaskFields(row: {
  project?: string;
  task?: string;
  mode?: string;
  domain?: string;
  task_label?: string;
  mode_label?: string;
}): string {
  return displayTask(row as LabelingBatchRow);
}

/** 列表「任务」列 */
export function displayTask(b: LabelingBatchRow): string {
  const project = b.project || "dms";
  if (project === "lane") return "车道线";

  if (isAdas3dScope(b)) return "3D 七类";
  if (isAdas2dScope(b)) return "2D 七类";

  if (isAdasScope(b)) {
    if (b.task === "forward") {
      return b.mode_label || (b.mode === "classify" ? "细分类" : "粗检测");
    }
    return "2D";
  }

  const task = b.task || "";
  const cabin: Record<string, string> = {
    addw: "ADDW",
    addw_face: "ADDW 人脸",
    ddaw: "DDAW",
    dam: "DAM",
  };
  if (cabin[task]) {
    if (task === "dam" && b.mode_label) return `DAM · ${b.mode_label}`;
    return cabin[task];
  }
  return b.task_label || task || "—";
}

/** 台账表单：业务线 → API project/task */
export type DeliveryLineKind =
  | "dms"
  | "adas_2d"
  | "adas_3d"
  | "forward"
  | "lane";

export function deliveryLineToApi(line: DeliveryLineKind): { project: string; task: string; mode: string } {
  switch (line) {
    case "adas_2d":
      return { project: "adas", task: "det_7cls", mode: "" };
    case "adas_3d":
      return { project: "adas", task: "cuboid_7cls", mode: "" };
    case "forward":
      return { project: "dms", task: "forward", mode: "" };
    case "lane":
      return { project: "lane", task: "lane_v1", mode: "" };
    default:
      return { project: "dms", task: "", mode: "" };
  }
}

export function defaultInboxPath(line: DeliveryLineKind, batch: string, task?: string, mode?: string): string {
  const b = batch.trim();
  if (line === "adas_2d") return `/data/hsap/datasets/adas/inbox/det_7cls/${b}`;
  if (line === "adas_3d") return `/data/hsap/datasets/adas/inbox/cuboid_7cls/${b}`;
  if (line === "lane") return `/data/hsap/datasets/lane/inbox/${b}`;
  if (line === "forward" && mode) return `/data/hsap/datasets/dms/inbox/forward/${mode}/${b}`;
  if (task) return `/data/hsap/datasets/dms/inbox/${task}/${b}`;
  return `/data/hsap/datasets/dms/inbox/{task}/${b}`;
}

/** @deprecated 用 deliveryLineToApi */
export function inferDeliveryProject(task: string, explicitProject?: string): string {
  const t = (task || "").trim().toLowerCase();
  if (explicitProject === "lane" || t === "lane" || t === "lane_v1") return "lane";
  if (explicitProject === "adas" || t === "cuboid_7cls" || t.includes("cuboid") || t === "moon3d") return "adas";
  return "dms";
}

/** 提交 build 时默认训练包 */
export function defaultBuildPack(b: LabelingBatchRow): string {
  if (b.pack) return b.pack;
  if (isAdas3dScope(b)) return "adas_moon3d_v1";
  if (isAdas2dScope(b)) return "adas_v1";
  if (b.project === "lane") return "lane_v1";
  return "dms_v2";
}

import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  defaultInboxPath,
  deliveryLineToApi,
  type DeliveryLineKind,
} from "@/lib/labelingDisplay";

export type DeliveryFormValues = {
  line: DeliveryLineKind;
  project: string;
  task: string;
  mode: string;
  batch_name: string;
  data_path: string;
  source_type: string;
  collection_start: string;
  collection_end: string;
  estimated_count: string;
  vehicle_scene: string;
  remark: string;
};

const EMPTY: DeliveryFormValues = {
  line: "dms",
  project: "dms",
  task: "",
  mode: "",
  batch_name: "",
  data_path: "",
  source_type: "platform_delivery",
  collection_start: "",
  collection_end: "",
  estimated_count: "",
  vehicle_scene: "",
  remark: "",
};

const LINES: { id: DeliveryLineKind; label: string; desc: string }[] = [
  { id: "dms", label: "DMS 舱内", desc: "addw / ddaw / dam / addw_face" },
  { id: "adas_2d", label: "ADAS 2D 七类", desc: "project=adas · det_7cls · adas/inbox/det_7cls/" },
  { id: "adas_3d", label: "ADAS 3D MOON", desc: "project=adas · cuboid_7cls · adas/inbox/" },
  { id: "forward", label: "前向交通标志", desc: "project=dms · task=forward · 须填子模式" },
  { id: "lane", label: "车道线", desc: "project=lane · lane/inbox/{批次}" },
];

type DeliveryCreateModalProps = {
  open: boolean;
  saving: boolean;
  onClose: () => void;
  onSubmit: (values: DeliveryFormValues) => void;
};

const fieldCls =
  "w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200";
const labelCls = "block text-xs font-medium text-gray-600 mb-1";

export const DeliveryCreateModal: React.FC<DeliveryCreateModalProps> = ({
  open,
  saving,
  onClose,
  onSubmit,
}) => {
  const [form, setForm] = useState<DeliveryFormValues>(EMPTY);
  const [intake, setIntake] = useState<"nas" | "inbox">("nas");

  useEffect(() => {
    if (!open) return;
    const api = deliveryLineToApi(form.line);
    setForm((f) => ({
      ...f,
      project: api.project,
      task: f.line === "dms" || f.line === "forward" ? f.task : api.task,
      mode: f.line === "forward" ? f.mode : api.mode,
    }));
  }, [form.line, open]);

  useEffect(() => {
    if (!open || intake !== "inbox" || !form.batch_name.trim()) return;
    if (form.data_path.trim()) return;
    const p = defaultInboxPath(
      form.line,
      form.batch_name.trim(),
      form.task || undefined,
      form.mode || undefined,
    );
    setForm((f) => ({ ...f, data_path: p }));
  }, [form.batch_name, form.line, form.mode, form.task, intake, open]);

  if (!open) return null;

  const set = (k: keyof DeliveryFormValues, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const onLineChange = (line: DeliveryLineKind) => {
    const api = deliveryLineToApi(line);
    setForm((f) => ({
      ...f,
      line,
      project: api.project,
      task: line === "dms" ? "" : api.task,
      mode: line === "forward" ? f.mode : api.mode,
      data_path: "",
    }));
  };

  const pathHint =
    intake === "nas"
      ? "/data/nas/采集批次/..."
      : defaultInboxPath(form.line, "{batch}", form.task || undefined, form.mode || undefined);

  const taskLocked = form.line === "adas_2d" || form.line === "adas_3d" || form.line === "lane";
  const modeRequired = form.line === "forward" || form.line === "dms";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const api = deliveryLineToApi(form.line);
    onSubmit({
      ...form,
      project: api.project,
      task: form.line === "dms" ? form.task.trim() : api.task,
      mode: form.line === "forward" || (form.line === "dms" && form.task === "dam") ? form.mode.trim() : api.mode,
      source_type: intake === "nas" ? "platform_delivery" : "inbox_scan",
    });
  };

  const resetClose = () => {
    setForm(EMPTY);
    setIntake("nas");
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={resetClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-lg font-semibold text-gray-900">新建送标申请</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            ADAS 2D 与 3D 同在 <code className="text-xs">adas/inbox/</code>：2D 在{" "}
            <code className="text-xs">det_7cls</code>，3D 在{" "}
            <code className="text-xs">adas/inbox/cuboid_7cls</code>
          </p>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className={labelCls}>业务线 *</label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {LINES.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => onLineChange(l.id)}
                  className={`rounded-lg border p-2.5 text-left text-xs transition-colors ${
                    form.line === l.id ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:bg-gray-50"
                  }`}
                >
                  <div className="font-medium text-sm">{l.label}</div>
                  <div className="text-gray-500 mt-0.5 leading-snug">{l.desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-2">
            {([
              { id: "nas" as const, label: "NAS / 外挂盘", desc: "审批后拷贝入湖" },
              { id: "inbox" as const, label: "已在 inbox", desc: "建议用「扫描数据湖」" },
            ]).map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setIntake(t.id)}
                className={`flex-1 rounded-lg border p-3 text-left transition-colors ${
                  intake === t.id ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:bg-gray-50"
                }`}
              >
                <div className="text-sm font-medium">{t.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelCls}>API 项目</label>
              <input className={`${fieldCls} bg-gray-50`} readOnly value={form.project} />
            </div>
            <div>
              <label className={labelCls}>任务 *</label>
              <input
                className={taskLocked ? `${fieldCls} bg-gray-50` : fieldCls}
                readOnly={taskLocked}
                placeholder={form.line === "dms" ? "addw / dam …" : ""}
                value={form.task}
                onChange={(e) => set("task", e.target.value)}
                required
              />
            </div>
            <div>
              <label className={labelCls}>子模式{form.line === "forward" ? " *" : ""}</label>
              <input
                className={fieldCls}
                placeholder={form.line === "forward" ? "detect / classify" : "dam: batch_0516"}
                value={form.mode}
                onChange={(e) => set("mode", e.target.value)}
                required={form.line === "forward"}
              />
            </div>
          </div>

          <div>
            <label className={labelCls}>批次名称 *</label>
            <input
              className={fieldCls}
              placeholder="20260601_pilot（勿与任务名相同）"
              value={form.batch_name}
              onChange={(e) => set("batch_name", e.target.value)}
              required
            />
          </div>

          <div>
            <label className={labelCls}>数据路径 *</label>
            <input
              className={`${fieldCls} font-mono text-xs`}
              placeholder={pathHint}
              value={form.data_path}
              onChange={(e) => set("data_path", e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>采集开始</label>
              <input type="date" className={fieldCls} value={form.collection_start} onChange={(e) => set("collection_start", e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>采集结束</label>
              <input type="date" className={fieldCls} value={form.collection_end} onChange={(e) => set("collection_end", e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>预估张数</label>
              <input type="number" min={0} className={fieldCls} value={form.estimated_count} onChange={(e) => set("estimated_count", e.target.value)} />
            </div>
            <div>
              <label className={labelCls}>车辆 / 场景</label>
              <input className={fieldCls} value={form.vehicle_scene} onChange={(e) => set("vehicle_scene", e.target.value)} />
            </div>
          </div>

          <div>
            <label className={labelCls}>备注</label>
            <textarea className={`${fieldCls} resize-none`} rows={2} value={form.remark} onChange={(e) => set("remark", e.target.value)} />
          </div>

          <div className="flex gap-2 justify-end pt-2 border-t border-gray-100">
            <Button type="button" variant="default" size="small" onClick={resetClose}>取消</Button>
            <Button type="submit" variant="primary" size="small" loading={saving}>保存草稿</Button>
          </div>
        </form>
      </div>
    </div>
  );
};

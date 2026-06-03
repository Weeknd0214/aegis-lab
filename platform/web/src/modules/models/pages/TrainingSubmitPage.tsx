import React, { useState } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";

const ACTION_LABELS: Record<string, string> = {
  train_dms: "DMS 训练", train_lane: "Lane 训练",
  eval_dms: "DMS 评估", eval_lane: "Lane 评估",
  promote_dms: "DMS 晋级", promote_lane: "Lane 晋级",
  pipeline_dms: "DMS 全流程",
};

export const TrainingSubmitPage: React.FC = () => {
  const [action, setAction] = useState("train_dms");
  const [project, setProject] = useState("dms");
  const [task, setTask] = useState("");
  const [pack, setPack] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const e: Record<string, string> = {};
    if (!task.trim()) e.task = "请输入任务名称";
    if (["train_dms", "train_lane", "eval_dms", "eval_lane"].includes(action) && !pack.trim()) e.pack = "请输入数据包名称";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await hsapApi.createTrainingRecord(action, { project, task: task.trim(), pack: pack.trim() }, note.trim() || undefined) as Record<string, unknown>;
      setResult(res);
    } catch (e) {
      setError(String(e));
    }
    setSubmitting(false);
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>训练提交</h1>
        <p>提交训练/评估任务，进入审核队列</p>
      </div>

      <div className="card max-w-lg">
        <div className="form-group">
          <label className="form-label">操作类型 *</label>
          <select className="form-input" value={action} onChange={(e) => { setAction(e.target.value); setErrors({}); }}>
            {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{k} — {v}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">项目 *</label>
          <select className="form-input" value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="dms">DMS</option>
            <option value="lane">Lane</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">任务 *</label>
          <input className={`form-input ${errors.task ? "border-red-500" : ""}`} value={task} onChange={(e) => { setTask(e.target.value); setErrors((p) => ({ ...p, task: "" })); }} placeholder="如 ddaw, dam, lane_v1" />
          {errors.task && <p className="text-red-500 text-xs mt-1">{errors.task}</p>}
        </div>
        <div className="form-group">
          <label className="form-label">数据包</label>
          <input className={`form-input ${errors.pack ? "border-red-500" : ""}`} value={pack} onChange={(e) => { setPack(e.target.value); setErrors((p) => ({ ...p, pack: "" })); }} placeholder="如 dms_v1" />
          {errors.pack && <p className="text-red-500 text-xs mt-1">{errors.pack}</p>}
        </div>
        <div className="form-group">
          <label className="form-label">备注</label>
          <textarea className="form-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="可选备注信息" rows={3} />
        </div>

        {error && <div className="bg-red-50 border border-red-200 rounded p-3 mb-3 text-sm text-red-700">{error}</div>}
        {result && (
          <div className="bg-green-50 border border-green-200 rounded p-3 mb-3">
            <p className="text-green-700 text-sm font-medium">提交成功！</p>
            <p className="text-xs text-gray-500 mt-1">Job ID: {result.id as string}</p>
            <Link to="/models/training/records" className="text-blue-600 text-xs hover:underline mt-1 inline-block">查看训练记录 →</Link>
          </div>
        )}

        <Button variant="primary" onClick={handleSubmit} loading={submitting}>提交审核</Button>
      </div>
    </div>
  );
};

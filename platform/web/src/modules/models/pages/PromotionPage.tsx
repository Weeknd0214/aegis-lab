import React, { useEffect, useState } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";

type ModelEntry = { name?: string; version?: string; task?: string; metrics?: Record<string, number>; status?: string };

export const PromotionPage: React.FC = () => {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("dms");
  const [task, setTask] = useState("");
  const [version, setVersion] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const [reg, rec] = await Promise.all([
        hsapApi.getModelRegistry(project, task || undefined),
        hsapApi.listTrainingRecords({ project, limit: 20 }),
      ]);
      setModels((reg.models || []) as ModelEntry[]);
      setHistory(((rec.items || []) as Record<string, unknown>[]).filter((r) => {
        const a = (r.action as string || "").toLowerCase();
        return a.includes("promote");
      }));
    } catch (e) { setError(String(e)); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [project]);

  const handleSubmit = async () => {
    if (!version.trim()) { setError("请选择或输入模型版本"); return; }
    setSubmitting(true); setError(null); setResult(null);
    try {
      const res = await hsapApi.createTrainingRecord(`promote_${project}`, { project, task: task.trim(), version: version.trim() }, note.trim() || undefined) as Record<string, unknown>;
      setResult(`晋级申请已提交 · Job: ${res.id as string}`);
      load();
    } catch (e) { setError(String(e)); }
    setSubmitting(false);
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>模型晋级</h1>
        <p>将评估通过的模型晋升为生产版本</p>
      </div>

      <PageQueryState loading={loading} error={error}>
        <div className="grid grid-cols-2 gap-6">
          {/* Left: Submit form */}
          <div className="card">
            <div className="card-header">提交晋级申请</div>
            <div className="form-group">
              <label className="form-label">项目</label>
              <select className="form-input" value={project} onChange={(e) => { setProject(e.target.value); setVersion(""); }}>
                <option value="dms">DMS</option>
                <option value="lane">Lane</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">任务</label>
              <input className="form-input" value={task} onChange={(e) => setTask(e.target.value)} placeholder="如 ddaw, dam" />
            </div>
            <div className="form-group">
              <label className="form-label">模型版本 *</label>
              <select className="form-input" value={version} onChange={(e) => setVersion(e.target.value)}>
                <option value="">选择版本...</option>
                {models.filter((m) => !task || m.task === task).map((m, i) => (
                  <option key={i} value={m.version || m.name || ""}>
                    {m.version || m.name || `#${i}`} {m.metrics?.map50 != null ? `(mAP50=${m.metrics.map50.toFixed(3)})` : ""}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1">或手动输入版本号：</p>
              <input className="form-input mt-1" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="如 v2.1.0" />
            </div>
            <div className="form-group">
              <label className="form-label">晋级理由</label>
              <textarea className="form-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="说明晋级原因（可选）" rows={3} />
            </div>
            {error && <div className="bg-red-50 border border-red-200 rounded p-3 mb-3 text-sm text-red-700">{error}</div>}
            {result && <div className="bg-green-50 border border-green-200 rounded p-3 mb-3 text-sm text-green-700">{result}</div>}
            <Button variant="primary" onClick={handleSubmit} loading={submitting}>提交晋级审核</Button>
          </div>

          {/* Right: Promotion history */}
          <div className="card">
            <div className="card-header">晋级历史</div>
            {history.length === 0 ? (
              <p className="text-sm text-gray-400">暂无晋级记录</p>
            ) : (
              <table className="table-auto">
                <thead>
                  <tr><th>Job ID</th><th>任务</th><th>版本</th><th>状态</th><th>时间</th></tr>
                </thead>
                <tbody>
                  {history.map((r) => {
                    const params = r.params as Record<string, unknown> | undefined;
                    return (
                      <tr key={r.id as string}>
                        <td className="font-mono text-xs">{(r.id as string).slice(0, 12)}...</td>
                        <td>{params?.task as string || "—"}</td>
                        <td className="font-mono text-xs">{params?.version as string || "—"}</td>
                        <td><StatusBadge status={(r.status as string) || "pending"} /></td>
                        <td className="text-xs text-gray-500">{r.created_at as string}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Candidate models */}
        {models.length > 0 && (
          <div className="card mt-4">
            <div className="card-header">候选模型 ({project})</div>
            <table className="table-auto">
              <thead>
                <tr><th>版本</th><th>任务</th><th>mAP@50</th><th>mAP@50-95</th><th>状态</th><th>操作</th></tr>
              </thead>
              <tbody>
                {models.filter((m) => !task || m.task === task).map((m, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs font-medium">{m.version || m.name || "—"}</td>
                    <td>{m.task || "—"}</td>
                    <td className="font-mono text-xs">{m.metrics?.map50?.toFixed(4) || "—"}</td>
                    <td className="font-mono text-xs">{m.metrics?.map50_95?.toFixed(4) || "—"}</td>
                    <td>{m.status || "experiment"}</td>
                    <td>
                      <Button size="small" variant="primary" onClick={() => { setVersion(m.version || m.name || ""); }}>
                        选择晋级
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </PageQueryState>
    </div>
  );
};

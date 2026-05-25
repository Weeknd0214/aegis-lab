import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, type CatalogReport, type JobRecord, type PendingReport } from "../api/client";
import { useToast } from "../components/Toast";
import { LANE_DATA_VIZ_ENABLED } from "../config/featureFlags";

type Ctx = { refreshMeta: () => void };
type IterAction = "train_dms" | "train_lane" | "eval_dms" | "eval_lane" | "visualize_dms" | "visualize_lane";

const ITERATE_ACTIONS = new Set<IterAction>([
  "train_dms",
  "train_lane",
  "eval_dms",
  "eval_lane",
  "visualize_dms",
  "visualize_lane",
]);

const ACTION_META: Record<IterAction, { label: string; project: "DMS" | "Lane"; kind: "训练" | "评估" | "可视化" }> = {
  train_dms: { label: "DMS 训练", project: "DMS", kind: "训练" },
  train_lane: { label: "Lane 训练", project: "Lane", kind: "训练" },
  eval_dms: { label: "DMS 评估", project: "DMS", kind: "评估" },
  eval_lane: { label: "Lane 评估", project: "Lane", kind: "评估" },
  visualize_dms: { label: "DMS 可视化", project: "DMS", kind: "可视化" },
  visualize_lane: { label: "Lane 可视化", project: "Lane", kind: "可视化" },
};

function statusBadgeClass(status: string): string {
  if (status === "succeeded") return "badge-promoted";
  if (status === "running") return "badge-training";
  if (status === "failed") return "badge-pending";
  return "badge-idle";
}

function fmtTime(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function extractWeight(job: JobRecord): string | null {
  const res = (job.result || {}) as Record<string, unknown>;
  const params = (job.params || {}) as Record<string, unknown>;
  const candidates = [res.best_weights, res.candidate, res.model_path, res.weights, params.weights, params.model_path];
  for (const v of candidates) {
    if (typeof v === "string" && v.trim()) return v;
  }
  return null;
}

export function IteratePage() {
  const { refreshMeta } = useOutletContext<Ctx>();
  const toast = useToast();
  const [pending, setPending] = useState<PendingReport | null>(null);
  const [cat, setCat] = useState<CatalogReport | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [dmsTask, setDmsTask] = useState("dam");
  const [dmsTrack, setDmsTrack] = useState<"platform" | "local">("platform");
  const [dmsWeights, setDmsWeights] = useState("");
  const [laneTrack, setLaneTrack] = useState<"platform" | "local">("platform");
  const [laneModelPath, setLaneModelPath] = useState("");
  const [laneDataRoot, setLaneDataRoot] = useState("");
  const [laneTestList, setLaneTestList] = useState("list/test_gt.txt");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const loadAll = async () => {
    const [p, c, j] = await Promise.all([api.pending(), api.catalog(), api.listJobs()]);
    setPending(p);
    setCat(c);
    setJobs(j.items || []);
  };

  useEffect(() => { loadAll(); }, []);

  useEffect(() => {
    const tasks = Object.keys(pending?.projects?.dms?.task_defs || {});
    if (tasks.length > 0 && !tasks.includes(dmsTask)) {
      setDmsTask(tasks[0]);
    }
  }, [pending]);

  const submit = async (action: string, params: Record<string, unknown>) => {
    try {
      await api.submitApproval(action, params);
      toast(`已提交 ${action}`);
      refreshMeta();
      await loadAll();
    } catch (e) {
      toast(String(e), true);
    }
  };

  const packRows = [
    ...(pending?.projects?.dms?.active_packs || []).map((n) => ({ project: "dms", name: n, enabled: true })),
    ...(pending?.projects?.dms?.not_enabled || []).map((n) => ({ project: "dms", name: n, enabled: false })),
    ...Object.entries(cat?.lane || {}).map(([n, info]) => ({ project: "lane", name: n, enabled: info.enabled })),
  ];

  const iterJobs = useMemo(() => {
    return jobs.filter((j) => ITERATE_ACTIONS.has(j.action as IterAction)).slice(0, 30);
  }, [jobs]);
  const milestones = useMemo(() => [...iterJobs].reverse(), [iterJobs]);
  const selectedJob = useMemo(
    () => milestones.find((j) => j.id === selectedJobId) || milestones[milestones.length - 1] || null,
    [milestones, selectedJobId]
  );

  useEffect(() => {
    if (!selectedJobId && milestones.length > 0) {
      setSelectedJobId(milestones[milestones.length - 1].id);
    }
  }, [milestones, selectedJobId]);

  const dmsTasks = Object.keys(pending?.projects?.dms?.task_defs || {});

  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <div className="panel-header"><h2>DMS（YOLO）一键训练/评估/可视化</h2></div>
          <div className="panel-body">
            <div className="crud-form">
              <label className="field">
                <span>任务</span>
                <select value={dmsTask} onChange={(e) => setDmsTask(e.target.value)}>
                  {(dmsTasks.length > 0 ? dmsTasks : [dmsTask]).map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="field">
                <span>执行轨</span>
                <select value={dmsTrack} onChange={(e) => setDmsTrack(e.target.value as "platform" | "local")}>
                  <option value="platform">platform（推荐）</option>
                  <option value="local">local</option>
                </select>
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>评估/可视化权重（可选）</span>
                <input value={dmsWeights} onChange={(e) => setDmsWeights(e.target.value)} placeholder="/path/to/best.pt" />
              </label>
            </div>
            <div className="audit-quick">
              <button type="button" className="btn btn-sm btn-primary" onClick={() => submit("train_dms", { task: dmsTask, mode: "full", track: dmsTrack })}>一键训练</button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => submit("eval_dms", { task: dmsTask, ...(dmsWeights ? { weights: dmsWeights } : {}) })}>一键评估</button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => submit("visualize_dms", { task: dmsTask, ...(dmsWeights ? { weights: dmsWeights } : {}) })}>检测可视化</button>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><h2>Lane（UFLD）一键训练/评估{LANE_DATA_VIZ_ENABLED ? "/可视化" : ""}</h2></div>
          <div className="panel-body">
            <div className="crud-form">
              <label className="field">
                <span>执行轨</span>
                <select value={laneTrack} onChange={(e) => setLaneTrack(e.target.value as "platform" | "local")}>
                  <option value="platform">platform（推荐）</option>
                  <option value="local">local</option>
                </select>
              </label>
              <label className="field">
                <span>test_list</span>
                <input value={laneTestList} onChange={(e) => setLaneTestList(e.target.value)} placeholder="list/test_gt.txt" />
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>模型路径（必填用于评估/可视化）</span>
                <input value={laneModelPath} onChange={(e) => setLaneModelPath(e.target.value)} placeholder="/path/to/best.pth" />
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>data_root（可选）</span>
                <input value={laneDataRoot} onChange={(e) => setLaneDataRoot(e.target.value)} placeholder="/path/to/lane/dataset/root" />
              </label>
            </div>
            <div className="audit-quick">
              <button type="button" className="btn btn-sm btn-primary" onClick={() => submit("train_lane", { track: laneTrack })}>一键训练</button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => submit("eval_lane", { model_path: laneModelPath, ...(laneDataRoot ? { data_root: laneDataRoot } : {}), test_list: laneTestList })}>一键评估</button>
              {LANE_DATA_VIZ_ENABLED && (
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => submit("visualize_lane", { model_path: laneModelPath, ...(laneDataRoot ? { data_root: laneDataRoot } : {}), test_list: laneTestList })}>检测可视化</button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header"><h2>训练数据包状态</h2></div>
        <div className="panel-body pack-list">
          {packRows.map((p) => (
            <div key={`${p.project}/${p.name}`} className={`pack-row ${p.enabled ? "active-pack" : ""}`}>
              <span className="pack-name">{p.project}/{p.name}</span>
              <span className={`badge ${p.enabled ? "badge-staged" : "badge-idle"}`}>{p.enabled ? "已启用" : "未启用"}</span>
              <code className="text-sm">python as.py enable {p.project} {p.name}</code>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-header"><h2>训练里程碑节点（可追溯）</h2></div>
        <div className="panel-body">
          {milestones.length === 0 ? (
            <div className="empty-state">暂无训练/评估节点</div>
          ) : (
            <div className="milestone-layout">
              <div className="milestone-track">
                {milestones.map((j) => {
                  const action = j.action as IterAction;
                  const meta = ACTION_META[action];
                  const weight = extractWeight(j);
                  return (
                    <button
                      type="button"
                      key={j.id}
                      className={`milestone-node ${selectedJob?.id === j.id ? "active" : ""}`}
                      onClick={() => setSelectedJobId(j.id)}
                    >
                      <div className="milestone-dot" />
                      <div className="milestone-body">
                        <div className="milestone-title">{meta?.label || j.action}</div>
                        <div className="milestone-sub">{fmtTime(j.started_at || j.created_at)}</div>
                        <div className="milestone-sub">
                          <span className={`badge ${statusBadgeClass(j.status)}`}>{j.status}</span>
                          <span>{meta?.project || "未知"}</span>
                          <span>{meta?.kind || "动作"}</span>
                        </div>
                        <div className="milestone-sub mono">{weight ? `权重: ${weight}` : "权重: —"}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
              {selectedJob && (
                <div className="milestone-detail">
                  <div className="milestone-detail-head">
                    <h3>{ACTION_META[selectedJob.action as IterAction]?.label || selectedJob.action}</h3>
                    <span className={`badge ${statusBadgeClass(selectedJob.status)}`}>{selectedJob.status}</span>
                  </div>
                  <dl className="detail-dl">
                    <dt>Job ID</dt>
                    <dd className="mono">{selectedJob.id}</dd>
                    <dt>创建时间</dt>
                    <dd>{fmtTime(selectedJob.created_at)}</dd>
                    <dt>开始时间</dt>
                    <dd>{fmtTime(selectedJob.started_at)}</dd>
                    <dt>结束时间</dt>
                    <dd>{fmtTime(selectedJob.finished_at)}</dd>
                    <dt>关键权重</dt>
                    <dd className="path-dd">{extractWeight(selectedJob) || "—"}</dd>
                    <dt>执行参数</dt>
                    <dd><pre className="params-pre">{JSON.stringify(selectedJob.params || {}, null, 2)}</pre></dd>
                    <dt>执行结果</dt>
                    <dd><pre className="params-pre milestone-result">{JSON.stringify(selectedJob.result || {}, null, 2)}</pre></dd>
                  </dl>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

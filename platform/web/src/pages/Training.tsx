import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import {
  api,
  type ModelRegistry,
  type PendingReport,
  type TrainingRecord,
} from "../api/client";
import { useToast } from "../components/Toast";
import { LANE_DATA_VIZ_ENABLED } from "../config/featureFlags";

type Ctx = { refreshMeta: () => void };

type TrainAction =
  | "train_dms"
  | "train_lane"
  | "eval_dms"
  | "eval_lane"
  | "visualize_dms"
  | "visualize_lane"
  | "promote_dms";

const CREATE_ACTIONS: { id: TrainAction; label: string; project: "dms" | "lane"; kind: string }[] = [
  { id: "train_dms", label: "DMS 训练", project: "dms", kind: "train" },
  { id: "eval_dms", label: "DMS 评估", project: "dms", kind: "eval" },
  { id: "visualize_dms", label: "DMS 可视化", project: "dms", kind: "visualize" },
  { id: "promote_dms", label: "DMS 晋级", project: "dms", kind: "promote" },
  { id: "train_lane", label: "Lane 训练", project: "lane", kind: "train" },
  { id: "eval_lane", label: "Lane 评估", project: "lane", kind: "eval" },
  ...(LANE_DATA_VIZ_ENABLED
    ? [{ id: "visualize_lane" as const, label: "Lane 可视化", project: "lane" as const, kind: "visualize" }]
    : []),
];

function statusBadge(status: string): string {
  if (status === "succeeded") return "badge-promoted";
  if (status === "running") return "badge-training";
  if (status === "failed") return "badge-pending";
  if (status === "queued") return "badge-pending";
  return "badge-idle";
}

function kindLabel(kind: string): string {
  return (
    {
      train: "训练",
      eval: "评估",
      visualize: "可视化",
      promote: "晋级",
      pipeline: "流水线",
    }[kind] || kind
  );
}

function fmtTime(ts?: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function fmtDuration(sec?: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}

function fmtMetric(metrics: Record<string, unknown>): string {
  const parts: string[] = [];
  if (metrics.map50 != null) parts.push(`mAP50=${metrics.map50}`);
  if (metrics.delta_map50 != null) parts.push(`Δ=${metrics.delta_map50}`);
  return parts.length > 0 ? parts.join(" · ") : "—";
}

export function TrainingPage() {
  const { refreshMeta } = useOutletContext<Ctx>();
  const toast = useToast();
  const [pending, setPending] = useState<PendingReport | null>(null);
  const [records, setRecords] = useState<TrainingRecord[]>([]);
  const [summary, setSummary] = useState({ total: 0, running: 0, queued: 0, succeeded: 0, failed: 0 });
  const [models, setModels] = useState<ModelRegistry | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [filterProject, setFilterProject] = useState<"" | "dms" | "lane">("");
  const [filterKind, setFilterKind] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterTask, setFilterTask] = useState("");

  const [createAction, setCreateAction] = useState<TrainAction>("train_dms");
  const [createNote, setCreateNote] = useState("");
  const [dmsTask, setDmsTask] = useState("dam");
  const [dmsTrack, setDmsTrack] = useState<"platform" | "local">("platform");
  const [dmsWeights, setDmsWeights] = useState("");
  const [laneTrack, setLaneTrack] = useState<"platform" | "local">("platform");
  const [laneModelPath, setLaneModelPath] = useState("");
  const [laneDataRoot, setLaneDataRoot] = useState("");
  const [laneTestList, setLaneTestList] = useState("list/test_gt.txt");

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [p, list, reg] = await Promise.all([
        api.pending(),
        api.listTrainingRecords({
          project: filterProject || undefined,
          kind: filterKind || undefined,
          status: filterStatus || undefined,
          task: filterTask || undefined,
          limit: 200,
        }),
        api.getModelRegistry("dms", filterTask || undefined),
      ]);
      setPending(p);
      setRecords(list.items || []);
      setSummary(list.summary || { total: 0, running: 0, queued: 0, succeeded: 0, failed: 0 });
      setModels(reg);
    } catch (e) {
      toast(String(e), true);
    } finally {
      setLoading(false);
    }
  }, [filterProject, filterKind, filterStatus, filterTask, toast]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const tasks = Object.keys(pending?.projects?.dms?.task_defs || {});
    if (tasks.length > 0 && !tasks.includes(dmsTask)) {
      setDmsTask(tasks[0]);
    }
  }, [pending, dmsTask]);

  useEffect(() => {
    const hasRunning = records.some((r) => r.status === "running" || r.status === "queued");
    if (!hasRunning) return;
    const t = setInterval(loadAll, 5000);
    return () => clearInterval(t);
  }, [records, loadAll]);

  const selected = useMemo(
    () => records.find((r) => r.id === selectedId) || records[0] || null,
    [records, selectedId]
  );

  useEffect(() => {
    if (!selectedId && records.length > 0) {
      setSelectedId(records[0].id);
    }
  }, [records, selectedId]);

  const dmsTasks = Object.keys(pending?.projects?.dms?.task_defs || {});
  const createMeta = CREATE_ACTIONS.find((a) => a.id === createAction);

  const buildCreateParams = (): Record<string, unknown> => {
    switch (createAction) {
      case "train_dms":
        return { task: dmsTask, mode: "full", track: dmsTrack };
      case "eval_dms":
        return { task: dmsTask, ...(dmsWeights ? { weights: dmsWeights } : {}) };
      case "visualize_dms":
        return { task: dmsTask, ...(dmsWeights ? { weights: dmsWeights } : {}) };
      case "promote_dms":
        return { task: dmsTask };
      case "train_lane":
        return { track: laneTrack };
      case "eval_lane":
        return {
          model_path: laneModelPath,
          test_list: laneTestList,
          ...(laneDataRoot ? { data_root: laneDataRoot } : {}),
        };
      case "visualize_lane":
        return {
          model_path: laneModelPath,
          test_list: laneTestList,
          ...(laneDataRoot ? { data_root: laneDataRoot } : {}),
        };
      default:
        return {};
    }
  };

  const handleCreate = async () => {
    if (createAction === "eval_lane" && !laneModelPath.trim()) {
      toast("Lane 评估需填写模型路径", true);
      return;
    }
    try {
      const approval = await api.createTrainingRecord(createAction, buildCreateParams(), createNote || undefined);
      toast(`已提交审核单 ${approval.id}`);
      refreshMeta();
      await loadAll();
      setCreateNote("");
    } catch (e) {
      toast(String(e), true);
    }
  };

  const currentTaskVersion =
    filterTask && models?.tasks?.[filterTask]
      ? models.tasks[filterTask]
      : dmsTask && models?.tasks?.[dmsTask]
        ? models.tasks[dmsTask]
        : null;

  return (
    <>
      <div className="kpi-strip">
        <div className="kpi">
          <span className="kpi-val">{summary.total}</span>
          <span className="kpi-lbl">训练记录</span>
        </div>
        <div className="kpi">
          <span className="kpi-val">{summary.running + summary.queued}</span>
          <span className="kpi-lbl">进行中</span>
        </div>
        <div className="kpi">
          <span className="kpi-val">{summary.succeeded}</span>
          <span className="kpi-lbl">成功</span>
        </div>
        <div className="kpi">
          <span className="kpi-val">{summary.failed}</span>
          <span className="kpi-lbl">失败</span>
        </div>
        <div className="kpi">
          <span className="kpi-val text-sm mono">{currentTaskVersion?.current ? "有线上" : "—"}</span>
          <span className="kpi-lbl">DMS 当前模型</span>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>新建训练 / 评估</h2>
        </div>
        <div className="panel-body">
          <div className="crud-form">
            <label className="field">
              <span>动作</span>
              <select value={createAction} onChange={(e) => setCreateAction(e.target.value as TrainAction)}>
                {CREATE_ACTIONS.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>备注</span>
              <input
                value={createNote}
                onChange={(e) => setCreateNote(e.target.value)}
                placeholder="可选：版本说明、实验目的"
              />
            </label>

            {createMeta?.project === "dms" && (
              <>
                <label className="field">
                  <span>任务</span>
                  <select value={dmsTask} onChange={(e) => setDmsTask(e.target.value)}>
                    {(dmsTasks.length > 0 ? dmsTasks : [dmsTask]).map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </label>
                {createAction === "train_dms" && (
                  <label className="field">
                    <span>执行轨</span>
                    <select value={dmsTrack} onChange={(e) => setDmsTrack(e.target.value as "platform" | "local")}>
                      <option value="platform">platform</option>
                      <option value="local">local</option>
                    </select>
                  </label>
                )}
                {["eval_dms", "visualize_dms"].includes(createAction) && (
                  <label className="field" style={{ gridColumn: "1 / -1" }}>
                    <span>权重路径（可选）</span>
                    <input
                      value={dmsWeights}
                      onChange={(e) => setDmsWeights(e.target.value)}
                      placeholder="/path/to/best.pt"
                    />
                  </label>
                )}
              </>
            )}

            {createMeta?.project === "lane" && (
              <>
                {createAction === "train_lane" && (
                  <label className="field">
                    <span>执行轨</span>
                    <select value={laneTrack} onChange={(e) => setLaneTrack(e.target.value as "platform" | "local")}>
                      <option value="platform">platform</option>
                      <option value="local">local</option>
                    </select>
                  </label>
                )}
                {createAction !== "train_lane" && (
                  <>
                    <label className="field" style={{ gridColumn: "1 / -1" }}>
                      <span>模型路径</span>
                      <input
                        value={laneModelPath}
                        onChange={(e) => setLaneModelPath(e.target.value)}
                        placeholder="/path/to/best.pth"
                      />
                    </label>
                    <label className="field">
                      <span>test_list</span>
                      <input value={laneTestList} onChange={(e) => setLaneTestList(e.target.value)} />
                    </label>
                    <label className="field">
                      <span>data_root（可选）</span>
                      <input value={laneDataRoot} onChange={(e) => setLaneDataRoot(e.target.value)} />
                    </label>
                  </>
                )}
              </>
            )}

            <div className="crud-actions">
              <button type="button" className="btn btn-primary" onClick={handleCreate}>
                提交训练任务
              </button>
              <span className="text-dim">提交后进入审核队列，批准后开始执行</span>
            </div>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>训练记录</h2>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => loadAll()}>
            刷新
          </button>
        </div>
        <div className="panel-body">
          <div className="catalog-toolbar">
            <label className="field">
              <span>项目</span>
              <select value={filterProject} onChange={(e) => setFilterProject(e.target.value as "" | "dms" | "lane")}>
                <option value="">全部</option>
                <option value="dms">DMS</option>
                <option value="lane">Lane</option>
              </select>
            </label>
            <label className="field">
              <span>类型</span>
              <select value={filterKind} onChange={(e) => setFilterKind(e.target.value)}>
                <option value="">全部</option>
                <option value="train">训练</option>
                <option value="eval">评估</option>
                <option value="visualize">可视化</option>
                <option value="promote">晋级</option>
              </select>
            </label>
            <label className="field">
              <span>状态</span>
              <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                <option value="">全部</option>
                <option value="queued">queued</option>
                <option value="running">running</option>
                <option value="succeeded">succeeded</option>
                <option value="failed">failed</option>
              </select>
            </label>
            <label className="field">
              <span>DMS 任务</span>
              <select value={filterTask} onChange={(e) => setFilterTask(e.target.value)}>
                <option value="">全部</option>
                {dmsTasks.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {loading && records.length === 0 ? (
            <p className="empty-state">加载中…</p>
          ) : records.length === 0 ? (
            <p className="empty-state">暂无训练记录，可在上方提交新任务</p>
          ) : (
            <div className="grid-2-equal">
              <div className="panel panel-compact">
                <div className="panel-header">
                  <h2>列表</h2>
                  <span className="text-dim">{records.length} 项</span>
                </div>
                <div className="panel-body table-wrap">
                  <table className="data-table compact">
                    <thead>
                      <tr>
                        <th>时间</th>
                        <th>动作</th>
                        <th>任务</th>
                        <th>状态</th>
                        <th>指标</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map((r) => (
                        <tr
                          key={r.id}
                          className={selected?.id === r.id ? "row-active" : ""}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelectedId(r.id)}
                        >
                          <td className="text-sm">{fmtTime(r.started_at || r.created_at).slice(0, 16)}</td>
                          <td>
                            <div>{r.action_label || r.action}</div>
                            <div className="text-dim">
                              {r.project} · {kindLabel(r.kind || "")}
                            </div>
                          </td>
                          <td>{r.task || "—"}</td>
                          <td>
                            <span className={`badge ${statusBadge(r.status)}`}>{r.status}</span>
                          </td>
                          <td className="text-sm">{fmtMetric(r.metrics || {})}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel panel-compact">
                <div className="panel-header">
                  <h2>详情</h2>
                </div>
                <div className="panel-body">
                  {selected ? (
                    <TrainingDetail record={selected} />
                  ) : (
                    <p className="empty-state">请选择一条记录</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {models && Object.keys(models.tasks || {}).length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <h2>DMS 模型版本</h2>
          </div>
          <div className="panel-body table-wrap">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>候选 (candidate)</th>
                  <th>线上 (current)</th>
                  <th>最近评估</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(models.tasks || {}).map(([task, ver]) => {
                  const v = ver as Record<string, unknown>;
                  const lastEval = (v.last_eval || {}) as Record<string, unknown>;
                  return (
                    <tr key={task}>
                      <td>
                        <strong>{task}</strong>
                      </td>
                      <td className="mono text-sm path-dd">{String(v.candidate || "—")}</td>
                      <td className="mono text-sm path-dd">{String(v.current || "—")}</td>
                      <td className="text-sm">
                        {lastEval.map50 != null ? `mAP50=${lastEval.map50}` : "—"}
                        {lastEval.weights ? (
                          <div className="text-dim mono">{String(lastEval.weights)}</div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(models?.eval_history?.length || 0) > 0 && (
        <div className="panel">
          <div className="panel-header">
            <h2>评估历史</h2>
          </div>
          <div className="panel-body table-wrap">
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>任务</th>
                  <th>mAP50</th>
                  <th>Δ</th>
                  <th>权重</th>
                </tr>
              </thead>
              <tbody>
                {(models?.eval_history || []).map((row, i) => (
                  <tr key={`${row.ts}-${i}`}>
                    <td className="text-sm">{fmtTime(row.ts as string)}</td>
                    <td>{String(row.task || "—")}</td>
                    <td>{row.map50 != null ? String(row.map50) : "—"}</td>
                    <td>{row.delta_map50 != null ? String(row.delta_map50) : "—"}</td>
                    <td className="mono text-sm path-dd">{String(row.weights || "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

function TrainingDetail({ record }: { record: TrainingRecord }) {
  const approval = record.approval;

  return (
    <div className="batch-detail">
      <div className="batch-detail-header">
        <h3>{record.action_label || record.action}</h3>
        <span className={`badge ${statusBadge(record.status)}`}>{record.status}</span>
      </div>
      <dl className="detail-dl">
        <dt>Job ID</dt>
        <dd className="mono">{record.id}</dd>
        <dt>项目 / 类型</dt>
        <dd>
          {record.project} · {kindLabel(record.kind || "")}
          {record.task ? ` · ${record.task}` : ""}
          {record.track ? ` · ${record.track}` : ""}
        </dd>
        <dt>创建 / 开始 / 结束</dt>
        <dd>
          {fmtTime(record.created_at)} → {fmtTime(record.started_at)} → {fmtTime(record.finished_at)}
        </dd>
        <dt>耗时</dt>
        <dd>{fmtDuration(record.duration_sec)}</dd>
        <dt>权重 / 产物</dt>
        <dd className="path-dd mono">{record.weight_path || "—"}</dd>
        <dt>指标</dt>
        <dd>{fmtMetric(record.metrics || {})}</dd>
        {record.error && (
          <>
            <dt>错误</dt>
            <dd className="text-sm" style={{ color: "var(--danger)" }}>
              {record.error}
            </dd>
          </>
        )}
        {approval && (
          <>
            <dt>审核单</dt>
            <dd>
              <Link to={`/audit/${approval.id}`}>{approval.id}</Link>
              <span className="text-dim"> · {approval.status}</span>
              {approval.note ? <div className="text-sm">{approval.note}</div> : null}
            </dd>
          </>
        )}
        <dt>执行参数</dt>
        <dd>
          <pre className="params-pre">{JSON.stringify(record.params || {}, null, 2)}</pre>
        </dd>
        <dt>执行结果</dt>
        <dd>
          <pre className="params-pre milestone-result">{JSON.stringify(record.result || {}, null, 2)}</pre>
        </dd>
      </dl>
    </div>
  );
}

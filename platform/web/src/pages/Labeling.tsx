import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, type BatchRecord, type PendingReport } from "../api/client";
import { forStage } from "../lib/labeling";
import { useToast } from "../components/Toast";
import { UploadsPage } from "./Uploads";

type Ctx = { refreshMeta: () => void };

export function LabelingPage() {
  const { refreshMeta } = useOutletContext<Ctx>();
  const toast = useToast();
  const [pending, setPending] = useState<PendingReport | null>(null);
  const [project, setProject] = useState<"dms" | "lane">("dms");
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [selectedPack, setSelectedPack] = useState<string | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);

  const load = async () => {
    setPending(await api.pending());
  };

  useEffect(() => {
    load();
  }, []);

  const batches = useMemo(() => {
    const all = pending?.batches || [];
    if (project === "dms" && selectedTask) return all.filter((b) => b.project === "dms" && b.task === selectedTask);
    if (project === "lane" && selectedPack) {
      return all.filter((b) => b.project === "lane" && (b.pack === selectedPack || b.batch === selectedPack));
    }
    return all;
  }, [pending, project, selectedTask, selectedPack]);

  const selected = batches.find((b) => `${b.location}:${b.batch}` === selectedBatchId) || batches[0];

  if (!pending) return <p className="empty-state">加载中…</p>;

  const bs = pending?.batches || [];
  const dmsTasks = Object.keys(pending.projects?.dms?.task_defs || {});
  const lanePacks = Object.keys(pending.projects?.lane?.packs || {});

  return (
    <>
      <div className="kpi-strip">
        <div className="kpi"><span className="kpi-val">{bs.filter((b) => b.stage === "returned").length}</span><span className="kpi-lbl">待审核入库</span></div>
        <div className="kpi"><span className="kpi-val">{bs.filter((b) => b.stage === "raw_pool").length}</span><span className="kpi-lbl">待标注原图</span></div>
        <div className="kpi"><span className="kpi-val">{bs.filter((b) => b.stage === "out_for_labeling").length}</span><span className="kpi-lbl">送标中</span></div>
        <div className="kpi"><span className="kpi-val">{(pending?.projects?.dms?.active_packs || []).length}</span><span className="kpi-lbl">启用训练包</span></div>
      </div>

      <div className="panel">
        <div className="panel-header"><h2>数据上传与自动分析</h2></div>
        <div className="panel-body">
          <UploadsPage embedded />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>待处理批次</h2>
          <div className="audit-filters">
            <button type="button" className={`btn btn-sm ${project === "dms" ? "btn-primary" : "btn-ghost"}`} onClick={() => { setProject("dms"); setSelectedPack(null); }}>DMS</button>
            <button type="button" className={`btn btn-sm ${project === "lane" ? "btn-primary" : "btn-ghost"}`} onClick={() => { setProject("lane"); setSelectedTask(null); }}>Lane</button>
          </div>
        </div>
        <div className="panel-body">
          <div className="catalog-toolbar">
            <label className="field">
              <span>{project === "dms" ? "任务" : "数据包"}</span>
              <select
                value={project === "dms" ? (selectedTask || "") : (selectedPack || "")}
                onChange={(e) => {
                  const value = e.target.value;
                  if (project === "dms") setSelectedTask(value || null);
                  else setSelectedPack(value || null);
                  setSelectedBatchId(null);
                }}
              >
                <option value="">全部</option>
                {(project === "dms" ? dmsTasks : lanePacks).map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="grid-2-equal">
            <div className="panel panel-compact">
              <div className="panel-header"><h2>批次列表</h2><span className="text-dim">{batches.length} 项</span></div>
              <div className="panel-body table-wrap">
                <table className="data-table">
                  <thead><tr><th>批次</th><th>阶段</th><th>位置</th><th>图</th><th>标注</th></tr></thead>
                  <tbody>
                    {batches.map((b) => {
                      const st = forStage(b.stage);
                      const id = `${b.location}:${b.batch}`;
                      return (
                        <tr key={id} className={selected === b ? "row-active" : ""} onClick={() => setSelectedBatchId(id)} style={{ cursor: "pointer" }}>
                          <td><strong>{b.batch}</strong></td>
                          <td><span className={`badge ${st.badge}`}>{st.label}</span></td>
                          <td>{b.location}</td>
                          <td>{b.counts?.images ?? "—"}</td>
                          <td>{b.counts?.labels ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="panel panel-compact">
              <div className="panel-header"><h2>详情与动作</h2></div>
              <div className="panel-body">
                {selected
                  ? <BatchDetail b={selected} onDone={() => { load(); refreshMeta(); toast("已提交"); }} />
                  : <p className="empty-state">请选择批次</p>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function BatchDetail({ b, onDone }: { b: BatchRecord; onDone: () => void }) {
  const st = forStage(b.stage);

  return (
    <div className="batch-detail">
      <div className="batch-detail-header">
        <h3>{b.batch}</h3>
        <span className={`badge ${st.badge}`}>{st.label}</span>
      </div>
      <dl className="detail-dl">
        <dt>数据路径</dt><dd className="mono path-dd">{b.path || "由上传解析后生成"}</dd>
        <dt>位置</dt><dd>{b.location}{b.pack ? ` · ${b.pack}` : ""}</dd>
        <dt>图像 / 标注</dt><dd>{b.counts?.images ?? "—"} / {b.counts?.labels ?? "—"}</dd>
      </dl>
      {b.next_cli && (
        <div className="cli-box">
          <code>{b.next_cli}</code>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => navigator.clipboard.writeText(b.next_cli!)}>复制命令</button>
        </div>
      )}
      <div className="batch-actions">
        {b.project === "dms" && b.stage === "returned" && (
          <button type="button" className="btn btn-sm btn-primary" onClick={async () => {
            await api.submitBuildBatch({ task: b.task, batch: b.batch, pack: b.pack || "dms_v2", location: b.location });
            onDone();
          }}>提交入库审核</button>
        )}
        <button type="button" className="btn btn-sm btn-ghost" onClick={async () => {
          await api.registerBatch({ project: b.project, task: b.task, batch: b.batch, pack: b.pack, location: b.location });
          onDone();
        }}>登记 meta（审核）</button>
      </div>
    </div>
  );
}

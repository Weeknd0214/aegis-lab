import { useEffect, useMemo, useState } from "react";
import { api, type DataCandidate } from "../api/client";
import { useToast } from "../components/Toast";

export function UploadsPage({ embedded = false }: { embedded?: boolean }) {
  const toast = useToast();
  const [project, setProject] = useState<"dms" | "lane">("dms");
  const [task, setTask] = useState("dam");
  const [tasks, setTasks] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [candidates, setCandidates] = useState<DataCandidate[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const loadCandidates = async () => {
    const res = await api.listDataCandidates(80);
    setCandidates(res.items || []);
  };

  useEffect(() => {
    loadCandidates();
  }, []);

  useEffect(() => {
    const loadTasks = async () => {
      try {
        const pending = await api.pending();
        const defs = pending.projects?.dms?.task_defs || {};
        const names = Object.keys(defs);
        setTasks(names);
        if (names.length > 0 && !names.includes(task)) {
          setTask(names[0]);
        }
      } catch {
        // keep manual fallback value
      }
    };
    loadTasks();
  }, []);

  useEffect(() => {
    if (!activeId) return;
    const t = setInterval(async () => {
      try {
        const latest = await api.getDataCandidate(activeId);
        setCandidates((prev) => [latest, ...prev.filter((x) => x.id !== latest.id)]);
        if (latest.status === "analyzed" || latest.status === "failed") {
          setActiveId(null);
          await loadCandidates();
        }
      } catch {
        // keep polling loop running; backend errors are surfaced in status list
      }
    }, 2000);
    return () => clearInterval(t);
  }, [activeId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      toast("请先选择压缩包文件");
      return;
    }
    setUploading(true);
    setProgress(0);
    try {
      const res = await api.uploadDatasetFile(file, project, project === "dms" ? task : undefined, setProgress);
      setActiveId(res.candidate.id);
      setCandidates((prev) => [res.candidate, ...prev.filter((x) => x.id !== res.candidate.id)]);
      toast(`上传成功，开始分析：${res.candidate.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const active = useMemo(() => candidates.find((x) => x.id === activeId) || null, [candidates, activeId]);

  return (
    <>
      <div className={embedded ? "" : "panel"}>
        <div className="panel-header"><h2>上传候选数据包</h2></div>
        <div className="panel-body">
          <form className="crud-form" onSubmit={submit}>
            <label className="field">
              <span>Project</span>
              <select value={project} onChange={(e) => {
                const next = e.target.value as "dms" | "lane";
                setProject(next);
                if (next === "dms" && tasks.length > 0 && !tasks.includes(task)) {
                  setTask(tasks[0]);
                }
              }}>
                <option value="dms">dms</option>
                <option value="lane">lane</option>
              </select>
            </label>
            {project === "dms" && (
              <label className="field">
                <span>Task</span>
                <select value={task} onChange={(e) => setTask(e.target.value)}>
                  {(tasks.length > 0 ? tasks : [task]).map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </label>
            )}
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>压缩包</span>
              <input type="file" accept=".zip,.tar,.tar.gz,.tgz" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </label>
            <div className="crud-actions">
              <button type="submit" className="btn btn-primary" disabled={uploading}>
                {uploading ? "上传中..." : "上传并自动分析"}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => loadCandidates()}>刷新</button>
            </div>
          </form>
          <div style={{ marginTop: 12 }}>
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
            <p className="audit-note">上传进度：{progress}% {active ? `| 当前分析状态：${active.status}` : ""}</p>
          </div>
        </div>
      </div>

      <div className={embedded ? "panel panel-compact" : "panel"}>
        <div className="panel-header"><h2>候选数据与分析状态</h2></div>
        <div className="panel-body table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>ID</th>
                <th>项目/任务</th>
                <th>状态</th>
                <th>格式</th>
                <th>train/val/test</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.id} className={c.id === activeId ? "row-active" : ""}>
                  <td className="mono">{c.id}</td>
                  <td>{c.project}{c.task ? `/${c.task}` : ""}</td>
                  <td><span className="badge badge-idle">{c.status}</span></td>
                  <td>{c.format_id || "—"}</td>
                  <td>
                    {c.split_counts
                      ? `${c.split_counts.train || 0}/${c.split_counts.val || 0}/${c.split_counts.test || 0}`
                      : "—"}
                  </td>
                  <td>{c.error_message || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

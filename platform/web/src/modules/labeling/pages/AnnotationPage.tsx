import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useHistory } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { useAuth } from "@/app/AuthContext";

interface CVATStatus {
  cvat_available: boolean;
  cvat_job_url?: string;
  cvat_status?: string;
  campaign_id: string;
  error?: string;
}

interface MyTaskItem {
  task_id: string;
  filename: string;
  relative_path: string;
  completed: boolean;
  frame_index: number;
}

interface SyncResult {
  saved?: number;
  shapes?: number;
}

const AUTO_SYNC_MS = 45_000;

function cvatUrlWithFrame(baseUrl: string, frameIndex: number): string {
  if (frameIndex < 0) return baseUrl;
  const sep = baseUrl.includes("?") ? "&" : "?";
  return `${baseUrl}${sep}frame=${frameIndex}`;
}

export const AnnotationPage: React.FC = () => {
  const { campaignId } = useParams<{ campaignId: string }>();
  const history = useHistory();
  const { hasPermission } = useAuth();
  const isCoordinator = hasPermission("write:labeling_assign");
  const backPath = isCoordinator ? "/labeling/campaigns" : "/labeling/my-tasks";

  const [status, setStatus] = useState<CVATStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [syncHint, setSyncHint] = useState<string>("CVAT 保存后约 45 秒自动同步");
  const syncInFlight = useRef(false);

  const [myTasks, setMyTasks] = useState<MyTaskItem[]>([]);
  const [myStats, setMyStats] = useState({ assigned: 0, completed: 0, pending: 0 });
  const [sidebarOpen, setSidebarOpen] = useState(!isCoordinator);
  const [activeFrame, setActiveFrame] = useState<number>(-1);
  const [iframeSrc, setIframeSrc] = useState<string>("");

  const loadMyTasks = useCallback(async () => {
    if (!campaignId) return;
    try {
      const res = await hsapApi.campaignMyTasks(campaignId);
      setMyTasks(res.items || []);
      setMyStats({
        assigned: res.assigned ?? 0,
        completed: res.completed ?? 0,
        pending: res.pending ?? 0,
      });
    } catch {
      setMyTasks([]);
      setMyStats({ assigned: 0, completed: 0, pending: 0 });
    }
  }, [campaignId]);

  useEffect(() => {
    void loadMyTasks();
  }, [loadMyTasks]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`/api/v1/labeling/cvat/status/${campaignId}`, {
          headers: { Authorization: `Bearer ${hsapApi.getToken()}` },
        });
        const data = await res.json();
        if (!res.ok) {
          if (!cancelled) {
            setFetchError(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
            setLoading(false);
          }
          return;
        }
        if (!cancelled) {
          setFetchError(null);
          setStatus(data as CVATStatus);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setFetchError(String(e));
          setLoading(false);
        }
      }
    };
    poll();
    const interval = setInterval(poll, 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [campaignId]);

  useEffect(() => {
    if (!status?.cvat_job_url) return;
    setIframeSrc(cvatUrlWithFrame(status.cvat_job_url, activeFrame));
  }, [status?.cvat_job_url, activeFrame]);

  const runSync = useCallback(async (silent = false): Promise<SyncResult | null> => {
    if (syncInFlight.current) {
      if (!silent) {
        setSyncHint("同步进行中，请稍候…");
      }
      return null;
    }
    syncInFlight.current = true;
    if (!silent) setSyncing(true);
    try {
      const res = await fetch(`/api/v1/labeling/cvat/sync/${campaignId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${hsapApi.getToken()}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`;
        if (!silent) alert(`同步失败: ${msg}`);
        else setSyncHint(`自动同步失败: ${msg}`);
        return null;
      }
      const saved = Number(data.saved ?? 0);
      const shapes = Number(data.shapes ?? 0);
      const hint = shapes > 0
        ? `已同步 ${saved} 张 · ${shapes} 个标注 · ${new Date().toLocaleTimeString()}`
        : `已检查，暂无新标注（请先在 CVAT 画布 Ctrl+S 保存）· ${new Date().toLocaleTimeString()}`;
      setSyncHint(hint);
      if (!silent) {
        if (shapes > 0) {
          alert(`标注已同步（${saved} 张，${shapes} 个对象）`);
        } else {
          alert(`同步完成：CVAT 侧暂无新标注。\n请确认已在画布中画框并保存（Ctrl+S），再点「立即同步」。`);
        }
      }
      void loadMyTasks();
      return data as SyncResult;
    } catch (e) {
      if (!silent) alert(`同步失败: ${e}`);
      else setSyncHint(`自动同步失败: ${e}`);
      return null;
    } finally {
      syncInFlight.current = false;
      if (!silent) setSyncing(false);
    }
  }, [campaignId, loadMyTasks]);

  useEffect(() => {
    if (!status?.cvat_available || !status.cvat_job_url) return;
    const tick = () => {
      if (document.visibilityState === "visible") {
        void runSync(true);
      }
    };
    const interval = setInterval(tick, AUTO_SYNC_MS);
    return () => clearInterval(interval);
  }, [status?.cvat_available, status?.cvat_job_url, runSync]);

  const handleBack = async () => {
    await runSync(true);
    history.push(backPath);
  };

  const openInNewTab = () => {
    const url = iframeSrc || status?.cvat_job_url;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  };

  const handleTaskClick = (item: MyTaskItem) => {
    if (item.frame_index < 0 || !status?.cvat_job_url) return;
    setActiveFrame(item.frame_index);
    setIframeSrc(cvatUrlWithFrame(status.cvat_job_url, item.frame_index));
  };

  const showSidebar = myStats.assigned > 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center flex-1 min-h-[60vh] bg-gray-900 text-white">
        <div className="text-center">
          <div className="animate-spin text-3xl mb-4">⏳</div>
          <p>正在连接 CVAT 标注引擎...</p>
        </div>
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="flex items-center justify-center flex-1 min-h-[60vh] bg-gray-900 text-white">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">🔒</div>
          <p className="mb-2">无法加载标注状态</p>
          <p className="text-red-400 text-sm">{fetchError}</p>
          <button onClick={() => history.push(backPath)} className="mt-4 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700">
            返回
          </button>
        </div>
      </div>
    );
  }

  if (!status?.cvat_available) {
    return (
      <div className="flex items-center justify-center flex-1 min-h-[60vh] bg-gray-900 text-white">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">⚠️</div>
          <p className="mb-2">CVAT 标注引擎不可用</p>
          {status?.error && <p className="text-red-400 text-sm">{status.error}</p>}
          <button onClick={() => history.push(backPath)} className="mt-4 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700">
            返回
          </button>
        </div>
      </div>
    );
  }

  if (!status.cvat_job_url) {
    return (
      <div className="flex items-center justify-center flex-1 min-h-[60vh] bg-gray-900 text-white">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">⏳</div>
          <p className="mb-2">CVAT Job 尚未就绪</p>
          <button onClick={() => history.push(backPath)} className="mt-4 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700">
            返回
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-900">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={handleBack}
            className="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded text-white shrink-0"
          >
            ← 返回
          </button>
          {showSidebar && (
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded text-gray-200 shrink-0"
            >
              {sidebarOpen ? "收起清单" : "我的清单"}
            </button>
          )}
          <span className="text-white font-medium truncate">
            标注画布
            {myStats.assigned > 0 && (
              <span className="text-gray-400 font-normal text-sm ml-2">
                我的 {myStats.completed}/{myStats.assigned}
              </span>
            )}
          </span>
          <span className="text-xs text-gray-400 hidden lg:inline truncate">{syncHint}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={openInNewTab}
            className="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded text-white"
          >
            新窗口打开
          </button>
          <button
            onClick={() => runSync(false)}
            disabled={syncing}
            className="px-4 py-1 text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-white"
          >
            {syncing ? "同步中..." : "立即同步"}
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {showSidebar && sidebarOpen && (
          <aside className="w-72 shrink-0 border-r border-gray-700 flex flex-col min-h-0 bg-gray-800">
            <div className="px-3 py-2 border-b border-gray-700 text-xs text-gray-400">
              我的清单 · 待标 {myStats.pending} 张
            </div>
            <ul className="flex-1 overflow-y-auto py-1">
              {myTasks.length === 0 ? (
                <li className="px-3 py-4 text-sm text-gray-500 text-center">
                  {isCoordinator ? "您在本批无个人分配" : "暂无分配给您的图，请联系协调员"}
                </li>
              ) : (
                myTasks.map((item) => (
                  <li key={item.task_id}>
                    <button
                      type="button"
                      onClick={() => handleTaskClick(item)}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-700 ${
                        activeFrame === item.frame_index ? "bg-gray-700 text-blue-300" : "text-gray-200"
                      }`}
                    >
                      <span className={`shrink-0 w-4 text-center ${item.completed ? "text-green-400" : "text-gray-500"}`}>
                        {item.completed ? "✓" : "○"}
                      </span>
                      <span className="truncate flex-1" title={item.filename}>
                        {item.filename || item.task_id.slice(0, 8)}
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          </aside>
        )}

        <iframe
          key={iframeSrc}
          src={iframeSrc || status.cvat_job_url}
          className="flex-1 w-full min-h-0 border-0"
          title="CVAT Annotation"
          allow="autoplay; camera; microphone"
        />
      </div>
    </div>
  );
};

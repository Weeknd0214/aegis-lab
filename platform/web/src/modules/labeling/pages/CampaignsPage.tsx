import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { StageBadge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";
import { AssignUserSelect } from "@/components/AssignUserSelect";
import { AssignCountControl } from "@/components/AssignCountControl";
import type { LabelingBatchRow } from "@/lib/types";

interface Assignee {
  id: number;
  name: string;
  roles: string[];
  department_names?: string[];
  avatar_url?: string;
}

interface AssignLine {
  userId: number;
  count: number;
}

export const CampaignsPage: React.FC = () => {
  const [batches, setBatches] = useState<LabelingBatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [feishuSyncHint, setFeishuSyncHint] = useState<{ message: string; url?: string } | null>(null);
  const [search, setSearch] = useState("");

  // assignees & assignment state
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [assigneesLoading, setAssigneesLoading] = useState(false);
  const [expandCampaign, setExpandCampaign] = useState<string | null>(null);
  const [assignLines, setAssignLines] = useState<AssignLine[]>([{ userId: 0, count: 0 }]);
  const [assigning, setAssigning] = useState(false);
  const [progressMap, setProgressMap] = useState<Record<string, Record<string, unknown>>>({});

  const filtered = batches.filter((b) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (b.batch || "").toLowerCase().includes(q) ||
      (b.task || "").toLowerCase().includes(q) ||
      (b.campaign_id || "").toLowerCase().includes(q)
    );
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.labelingBatches({ stage: "out_for_labeling", limit: 100 });
      setBatches((res.items || []) as LabelingBatchRow[]);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, []);

  const loadAssignees = useCallback(async () => {
    setAssigneesLoading(true);
    try {
      const res = await hsapApi.labelingAssignees();
      setAssignees((res.items || []) as Assignee[]);
      const sync = (res as {
        sync?: {
          error?: string;
          total?: number;
          feishu_configured?: boolean;
          contact_scope_url?: string;
          publish_url?: string;
        };
      }).sync;
      const total = sync?.total ?? (res.items || []).length;
      if (sync?.feishu_configured && sync.error && total === 0) {
        setFeishuSyncHint({
          message: sync.error,
          url: sync.publish_url || sync.contact_scope_url,
        });
      } else if (
        sync?.feishu_configured &&
        sync.error &&
        (sync.error.includes("通讯录") || sync.error.includes("全部员工") || total <= 5)
      ) {
        setFeishuSyncHint({
          message: sync.error,
          url: sync.publish_url || sync.contact_scope_url,
        });
      } else if (total > 0) {
        setFeishuSyncHint(null);
      }
    } catch (e) {
      setError(String(e));
    }
    setAssigneesLoading(false);
  }, []);

  useEffect(() => {
    load();
    loadAssignees();
  }, [load, loadAssignees]);

  // load progress + refresh assignees when expanding assignment panel
  useEffect(() => {
    if (!expandCampaign) return;
    loadAssignees();
    hsapApi
      .campaignProgress(expandCampaign)
      .then((p) => setProgressMap((prev) => ({ ...prev, [expandCampaign!]: p })))
      .catch(() => {});
  }, [expandCampaign, loadAssignees]);

  const handleExport = async (campaignId: string) => {
    setInfo(null);
    try {
      await hsapApi.labelingExport(campaignId);
      setInfo("导出任务已提交");
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSubmit = async (campaignId: string) => {
    try {
      await hsapApi.submitLabelingCampaign(campaignId);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleAddLine = () => {
    setAssignLines((prev) => [...prev, { userId: 0, count: 0 }]);
  };

  const handleRemoveLine = (idx: number) => {
    setAssignLines((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleLineChange = (idx: number, field: "userId" | "count", value: number) => {
    setAssignLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  };

  const handleAssign = async (campaignId: string) => {
    const valid = assignLines.filter((l) => l.userId > 0 && l.count > 0);
    if (valid.length === 0) {
      setError("请至少选择一个用户并设置数量");
      return;
    }
    setAssigning(true);
    setError(null);
    try {
      const items = valid.map((l) => ({ user_id: l.userId, count: l.count }));
      const res = await hsapApi.assignTasksQuantized(campaignId, items);
      const assigned = (res as { assigned?: number }).assigned ?? 0;
      const notifications = (res as {
        notifications?: {
          ok?: boolean;
          name?: string;
          message?: string;
          help_url?: string;
          help_text?: string;
          channel?: string;
        }[];
      }).notifications ?? [];
      const sent = notifications.filter((n) => n.ok);
      const failed = notifications.filter((n) => !n.ok);
      let msg = `已分配 ${assigned} 个任务`;
      if (sent.length > 0) {
        msg += `，已通知 ${sent.map((n) => n.name).join("、")}`;
      }
      if (failed.length > 0) {
        const hint = failed[0]?.help_text || failed[0]?.message || "发送失败";
        msg += `；通知未送达（${hint}）`;
        if (failed[0]?.help_url) {
          setFeishuSyncHint({
            message: hint,
            url: failed[0].help_url,
          });
        }
      } else if (notifications.length === 0 && valid.some((l) => assignees.find((a) => a.id === l.userId))) {
        msg += "；被分配人未绑定飞书账号，无法通知";
      }
      setInfo(msg);
      setAssignLines([{ userId: 0, count: 0 }]);
      // refresh progress
      const p = await hsapApi.campaignProgress(campaignId);
      setProgressMap((prev) => ({ ...prev, [campaignId]: p }));
      load();
    } catch (e) {
      setError(String(e));
    }
    setAssigning(false);
  };

  const toggleExpand = (cid: string) => {
    setExpandCampaign((prev) => (prev === cid ? null : cid));
    setAssignLines([{ userId: 0, count: 0 }]);
    setError(null);
  };

  const unassignedCount = (campaignId: string) => {
    const prog = progressMap[campaignId] as { unassigned_tasks?: number } | undefined;
    return prog?.unassigned_tasks ?? null;
  };

  const maxCountForLine = (campaignId: string, lineIdx: number) => {
    const total = unassignedCount(campaignId);
    if (total == null) return 99;
    const used = assignLines
      .filter((_, i) => i !== lineIdx)
      .reduce((sum, l) => sum + (l.count || 0), 0);
    return Math.max(0, total - used);
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>标注进度</h1>
          <p>查看和管理进行中的标注活动</p>
        </div>
        <Button size="small" variant="default" onClick={load}>
          刷新
        </Button>
      </div>

      {/* Search */}
      <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-[200px] relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="搜索批次、任务或 Campaign ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <span className="text-xs text-gray-500 font-medium bg-gray-50 px-2.5 py-1 rounded-full">
            {filtered.length} 条
          </span>
        </div>
      </div>

      {feishuSyncHint && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-sm text-amber-900">
          <p>{feishuSyncHint.message}</p>
          {feishuSyncHint.url && (
            <a
              href={feishuSyncHint.url}
              target="_blank"
              rel="noreferrer"
              className="text-blue-600 hover:text-blue-800 underline mt-1 inline-block"
            >
              前往飞书开放平台开通通讯录权限
            </a>
          )}
        </div>
      )}

      {info && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4 text-sm text-green-700">
          {info}
        </div>
      )}

      <PageQueryState loading={loading} error={error} empty={filtered.length === 0} emptyMessage="暂无进行中的标注活动">
        <div className="space-y-3">
          {filtered.map((b) => {
            const pct =
              b.total_tasks && b.total_tasks > 0
                ? Math.round(((b.completed_tasks || 0) / b.total_tasks) * 100)
                : 0;
            const isExpanded = expandCampaign === b.campaign_id;
            const prog = (b.campaign_id ? progressMap[b.campaign_id] : null) as Record<string, unknown> | null;
            const byUser = (prog?.by_user || []) as { user_id: number; name: string; assigned: number; completed: number; percent: number }[];

            return (
              <div
                key={b.campaign_id || b.batch}
                className={`card hover:shadow-sm transition-shadow ${isExpanded ? "ring-2 ring-blue-300" : ""}`}
              >
                {/* Main row */}
                <div className="flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm">{b.batch}</span>
                      <span className="text-xs text-gray-400 font-mono">{b.task || "—"}</span>
                      <StageBadge stage={b.stage} />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-400">
                      {b.campaign_id && (
                        <span className="font-mono">{b.campaign_id.slice(0, 14)}...</span>
                      )}
                      {b.assigned_to_name && <span>👤 {b.assigned_to_name}</span>}
                    </div>
                    {b.total_tasks != null && b.total_tasks > 0 && (
                      <div className="mt-2 flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden max-w-[200px]">
                          <div
                            className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-green-500" : "bg-blue-500"}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">
                          {b.completed_tasks}/{b.total_tasks}
                        </span>
                        {b.assigned_tasks != null && (
                          <span className="text-xs text-gray-400">
                            已分配 {b.assigned_tasks}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {b.campaign_id && (
                      <>
                        <Link
                          to={`/labeling/annotate/${encodeURIComponent(b.campaign_id)}`}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
                        >
                          ✏️ 标注
                        </Link>
                        <button
                          onClick={() => handleExport(b.campaign_id!)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-50 text-gray-600 hover:bg-gray-100 transition-colors"
                        >
                          📤 导出
                        </button>
                        <button
                          onClick={() => handleSubmit(b.campaign_id!)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-50 text-green-700 hover:bg-green-100 transition-colors"
                        >
                          ✅ 提交
                        </button>
                        <button
                          onClick={() => toggleExpand(b.campaign_id!)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-purple-50 text-purple-700 hover:bg-purple-100 transition-colors"
                        >
                          👥 {isExpanded ? "收起" : "分配"}
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Expanded: task assignment panel */}
                {isExpanded && b.campaign_id && (
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    {/* ── current assignment progress ── */}
                    {byUser.length > 0 && (
                      <div className="mb-4">
                        <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">当前分配</h4>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                          {byUser.map((u) => (
                            <div
                              key={u.user_id}
                              className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg text-xs"
                            >
                              <span className="font-medium text-gray-700 truncate">{u.name}</span>
                              <span className="text-gray-400">
                                {u.completed}/{u.assigned}
                              </span>
                              <div className="flex-1 h-1 bg-gray-200 rounded-full max-w-[40px]">
                                <div
                                  className="h-full rounded-full bg-blue-400"
                                  style={{ width: `${u.percent}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* ── assign form ── */}
                    <div className="rounded-xl border border-gray-100 bg-gray-50/60 p-4">
                      <div className="flex items-center justify-between gap-3 mb-3">
                        <div>
                          <h4 className="text-sm font-semibold text-gray-800">新增分配</h4>
                          <p className="text-xs text-gray-500 mt-0.5">
                            从飞书通讯录选择成员，填写分配数量后提交
                            {assignees.length > 0 && (
                              <span className="text-gray-400"> · 共 {assignees.length} 人可选</span>
                            )}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => loadAssignees()}
                          disabled={assigneesLoading}
                          className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:border-gray-300 disabled:opacity-50"
                        >
                          <svg className={`w-3.5 h-3.5 ${assigneesLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          同步通讯录
                        </button>
                      </div>

                      {assignees.length === 0 && !assigneesLoading ? (
                        <div className="text-center py-8 px-4 bg-white rounded-lg border border-dashed border-gray-200">
                          <p className="text-sm text-gray-500 mb-2">暂无可选成员</p>
                          <p className="text-xs text-gray-400">请点击「同步通讯录」或联系管理员开通飞书通讯录权限</p>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <div className="grid grid-cols-[10rem_1fr_2rem] gap-3 px-3 text-[11px] font-medium text-gray-400 uppercase tracking-wide">
                            <span>成员</span>
                            <span>分配数量</span>
                            <span />
                          </div>
                          {assignLines.map((line, idx) => (
                            <div
                              key={idx}
                              className="grid grid-cols-[10rem_1fr_2rem] gap-3 items-center px-3 py-2.5 bg-white rounded-lg border border-gray-200"
                            >
                              <AssignUserSelect
                                value={line.userId}
                                options={assignees}
                                excludedIds={assignLines
                                  .filter((_, i) => i !== idx)
                                  .map((l) => l.userId)
                                  .filter((id) => id > 0)}
                                onChange={(userId) => handleLineChange(idx, "userId", userId)}
                                disabled={assigneesLoading || assignees.length === 0}
                              />
                              <AssignCountControl
                                value={line.count}
                                max={maxCountForLine(b.campaign_id!, idx)}
                                onChange={(count) => handleLineChange(idx, "count", count)}
                                disabled={assigneesLoading}
                              />
                              {assignLines.length > 1 ? (
                                <button
                                  type="button"
                                  onClick={() => handleRemoveLine(idx)}
                                  className="h-10 w-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                                  title="移除"
                                >
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                  </svg>
                                </button>
                              ) : (
                                <span />
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="flex items-center gap-2 mt-4">
                        <button
                          type="button"
                          onClick={handleAddLine}
                          disabled={assignees.length === 0}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-blue-600 hover:bg-blue-50 disabled:text-gray-300 disabled:hover:bg-transparent"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                          </svg>
                          添加一行
                        </button>
                        {expandCampaign && unassignedCount(expandCampaign) != null && (
                          <span className="text-xs text-gray-400">
                            剩余未分配 {unassignedCount(expandCampaign)} 张
                          </span>
                        )}
                        <div className="flex-1" />
                        <Button
                          size="small"
                          variant="primary"
                          loading={assigning}
                          disabled={assignees.length === 0}
                          onClick={() => handleAssign(b.campaign_id!)}
                        >
                          确认分配
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </PageQueryState>
    </div>
  );
};

import React, { useEffect, useState, useCallback } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";
import { LabelingListToolbar } from "../components/LabelingListToolbar";
import { CampaignBatchTable } from "../components/CampaignBatchTable";
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
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [assigneesLoading, setAssigneesLoading] = useState(false);
  const [expandCampaign, setExpandCampaign] = useState<string | null>(null);
  const [assignLines, setAssignLines] = useState<AssignLine[]>([{ userId: 0, count: 0 }]);
  const [assigning, setAssigning] = useState(false);
  const [progressMap, setProgressMap] = useState<Record<string, Record<string, unknown>>>({});

  const load = useCallback(async (newOffset: number, newLimit: number) => {
    setLoading(true);
    setError(null);
    try {
      const q = search.trim() || undefined;
      const res = await hsapApi.labelingBatches({ stage: "out_for_labeling", offset: newOffset, limit: newLimit, q });
      setBatches((res.items || []) as LabelingBatchRow[]);
      setTotal(res.total ?? 0);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [search]);

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

  useEffect(() => { loadAssignees(); }, [loadAssignees]);
  useEffect(() => { void load(0, limit); }, [search]);

  // load progress + refresh assignees when expanding assignment panel
  useEffect(() => {
    if (!expandCampaign) return;
    hsapApi
      .campaignProgress(expandCampaign)
      .then((p) => setProgressMap((prev) => ({ ...prev, [expandCampaign!]: p })))
      .catch(() => {});
  }, [expandCampaign]);

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
      load(offset, limit);
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
      load(offset, limit);
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

  const renderAssignPanel = (b: LabelingBatchRow) => {
    const prog = (b.campaign_id ? progressMap[b.campaign_id] : null) as Record<string, unknown> | null;
    const byUser = (prog?.by_user || []) as { user_id: number; name: string; assigned: number; completed: number; percent: number }[];
    if (!b.campaign_id) return null;

    return (
      <div className="p-4">
        {byUser.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">当前分配</h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {byUser.map((u) => (
                <div key={u.user_id} className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg text-xs border border-gray-100">
                  <span className="font-medium text-gray-700 truncate">{u.name}</span>
                  <span className="text-gray-400">{u.completed}/{u.assigned}</span>
                  <div className="flex-1 h-1 bg-gray-200 rounded-full max-w-[40px]">
                    <div className="h-full rounded-full bg-blue-400" style={{ width: `${u.percent}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="rounded-xl border border-gray-100 bg-white p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <h4 className="text-sm font-semibold text-gray-800">新增分配</h4>
              <p className="text-xs text-gray-500 mt-0.5">
                从飞书通讯录选择成员，填写分配数量后提交
                {assignees.length > 0 && <span className="text-gray-400"> · 共 {assignees.length} 人可选</span>}
              </p>
            </div>
            <button
              type="button"
              onClick={() => loadAssignees()}
              disabled={assigneesLoading}
              className="shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            >
              同步通讯录
            </button>
          </div>

          {assignees.length === 0 && !assigneesLoading ? (
            <div className="text-center py-6 text-sm text-gray-500">暂无可选成员，请同步通讯录</div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-[10rem_1fr_2rem] gap-3 px-3 text-[11px] font-medium text-gray-400 uppercase tracking-wide">
                <span>成员</span>
                <span>分配数量</span>
                <span />
              </div>
              {assignLines.map((line, idx) => (
                <div key={idx} className="grid grid-cols-[10rem_1fr_2rem] gap-3 items-center px-3 py-2.5 bg-gray-50 rounded-lg border border-gray-200">
                  <AssignUserSelect
                    value={line.userId}
                    options={assignees}
                    excludedIds={assignLines.filter((_, i) => i !== idx).map((l) => l.userId).filter((id) => id > 0)}
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
                    <button type="button" onClick={() => handleRemoveLine(idx)} className="text-gray-400 hover:text-red-500">×</button>
                  ) : <span />}
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center gap-2 mt-4">
            <button type="button" onClick={handleAddLine} disabled={assignees.length === 0} className="text-xs text-blue-600 hover:underline disabled:text-gray-300">
              添加一行
            </button>
            {expandCampaign && unassignedCount(expandCampaign) != null && (
              <span className="text-xs text-gray-400">剩余未分配 {unassignedCount(expandCampaign)} 张</span>
            )}
            <div className="flex-1" />
            <Button size="small" variant="primary" loading={assigning} disabled={assignees.length === 0} onClick={() => handleAssign(b.campaign_id!)}>
              确认分配
            </Button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>标注进度</h1>
          <p>查看和管理进行中的标注活动</p>
        </div>
        <Button size="small" variant="default" onClick={() => load(offset, limit)}>
          刷新
        </Button>
      </div>

      <LabelingListToolbar
        search={search}
        onSearchChange={setSearch}
        placeholder="搜索批次/任务/Campaign..."
        total={total}
      />

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

      <PageQueryState loading={loading} error={error} empty={!loading && total === 0} emptyMessage="暂无进行中的标注活动">
        {total > 0 && (
          <>
            <CampaignBatchTable
              batches={batches}
              expandCampaign={expandCampaign}
              onToggleExpand={toggleExpand}
              onExport={handleExport}
              onSubmit={handleSubmit}
              renderExpand={renderAssignPanel}
            />
            <ListPaginationBar
              total={total}
              offset={offset}
              limit={limit}
              onOffsetChange={(o) => load(o, limit)}
              onLimitChange={(l) => load(0, l)}
            />
          </>
        )}
      </PageQueryState>
    </div>
  );
};

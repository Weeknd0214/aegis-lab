import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { PageQueryState } from "@/components/PageQueryState";

type VersionEntry = Record<string, unknown>;

export const DatasetVersionsPage: React.FC = () => {
  const [versions, setVersions] = useState<VersionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState("dms");
  const [diffA, setDiffA] = useState("");
  const [diffB, setDiffB] = useState("");
  const [diffResult, setDiffResult] = useState<Record<string, unknown> | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const filtered = versions.filter((v) => !search || String(v.description || v.version_id || "").toLowerCase().includes(search.toLowerCase()));

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await hsapApi.listDatasetVersions(project);
      setVersions((res.items || []) as VersionEntry[]);
    } catch (e) { setError(String(e)); }
    setLoading(false);
  }, [project]);

  useEffect(() => { load(); }, [load]);

  const handleDiff = async () => {
    if (!diffA || !diffB) return;
    try {
      const res = await hsapApi.diffDatasetVersions(diffA, diffB, project);
      setDiffResult(res);
    } catch (e) { setError(String(e)); }
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>数据集版本</h1>
          <p>build 入库后自动生成快照，追踪数据演化历史</p>
        </div>
        <div className="flex gap-2">
          <select className="form-input w-auto" value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="dms">DMS</option>
            <option value="lane">Lane</option>
          </select>
          <Button variant="default" size="small" onClick={load}>刷新</Button>
        </div>
      </div>
      <div className="flex gap-2 mb-3">
        <input className="form-input w-48" placeholder="搜索版本描述..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <span className="text-xs text-gray-400 self-center">共 {filtered.length} 条</span>
      </div>

      {/* Version diff */}
      <div className="card mb-4">
        <div className="card-header">版本对比</div>
        <div className="flex gap-2 items-end">
          <div className="form-group flex-1">
            <label className="form-label">版本 A (旧)</label>
            <select className="form-input" value={diffA} onChange={(e) => setDiffA(e.target.value)}>
              <option value="">选择版本...</option>
              {versions.map((v) => <option key={v._id as string} value={v._id as string}>{v.version_id as string} - {v.description as string || "无描述"}</option>)}
            </select>
          </div>
          <div className="form-group flex-1">
            <label className="form-label">版本 B (新)</label>
            <select className="form-input" value={diffB} onChange={(e) => setDiffB(e.target.value)}>
              <option value="">选择版本...</option>
              {versions.map((v) => <option key={v._id as string} value={v._id as string}>{v.version_id as string} - {v.description as string || "无描述"}</option>)}
            </select>
          </div>
          <Button variant="default" onClick={handleDiff} disabled={!diffA || !diffB}>对比</Button>
        </div>
        {diffResult && (
          <div className="mt-4 bg-gray-50 rounded-lg p-4">
            <div className="grid grid-cols-3 gap-4 mb-3 text-sm">
              <div>
                <span className="font-semibold">{(diffResult.v1 as Record<string,unknown>)?.id as string || "—"}</span>
                <p className="text-xs text-gray-500">图片: {(diffResult.v1 as Record<string,unknown>)?.total as number || 0}</p>
              </div>
              <div className="text-center text-2xl text-gray-400">→</div>
              <div>
                <span className="font-semibold">{(diffResult.v2 as Record<string,unknown>)?.id as string || "—"}</span>
                <p className="text-xs text-gray-500">图片: {(diffResult.v2 as Record<string,unknown>)?.total as number || 0}</p>
              </div>
            </div>
            {diffResult.image_delta != null && (
              <p className="text-sm mb-2">
                图片变化: <span className={Number(diffResult.image_delta) >= 0 ? "text-green-600" : "text-red-600"}>
                  {Number(diffResult.image_delta) >= 0 ? "+" : ""}{diffResult.image_delta as number} 张
                </span>
              </p>
            )}
            {((diffResult.added_packs as string[])?.length > 0) && (
              <p className="text-sm text-green-600">+ 新增包: {(diffResult.added_packs as string[]).join(", ")}</p>
            )}
            {((diffResult.removed_packs as string[])?.length > 0) && (
              <p className="text-sm text-red-600">- 移除包: {(diffResult.removed_packs as string[]).join(", ")}</p>
            )}
            {((diffResult.pack_changes as unknown[])?.length > 0) && (
              <div className="mt-2">
                <p className="text-xs font-semibold text-gray-500 mb-1">数据包变化详情:</p>
                {(diffResult.pack_changes as Record<string, unknown>[]).map((pc, i) => (
                  <div key={i} className="text-xs text-gray-600 ml-2">
                    {pc.pack as string}: train {(pc.v1 as Record<string,number>).train}→{(pc.v2 as Record<string,number>).train}, val {(pc.v1 as Record<string,number>).val}→{(pc.v2 as Record<string,number>).val}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Version list */}
      <PageQueryState loading={loading} error={error} empty={filtered.length === 0} emptyMessage="暂无数据集版本，请创建第一个快照">
        <div className="space-y-4">
          {filtered.map((v) => {
            const summary = v.summary as Record<string, unknown> | undefined;
            const diff = v.diff as Record<string, unknown> | undefined;
            const isExpanded = expandedId === v._id;
            return (
              <div key={v._id as string} className="card">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <Badge variant="info">{v.version_id as string}</Badge>
                    <span className="text-sm font-medium">{v.description as string || "无描述"}</span>
                    {(v.parent_version as string) && (
                      <span className="text-xs text-gray-400">
                        基于 <span className="font-mono">{v.parent_version as string}</span>
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{v.created_at as string}</span>
                    <span>{v.author as string || "—"}</span>
                    <button onClick={() => setExpandedId(isExpanded ? null : (v._id as string))}
                      className="text-blue-600 hover:underline">{isExpanded ? "收起" : "详情"}</button>
                  </div>
                </div>

                {/* Summary stats */}
                <div className="flex gap-4 text-sm">
                  <span>📦 {summary?.packs_count as number || 0} 个包</span>
                  <span>🖼️ {summary?.total_images as number || 0} 张图</span>
                  <span>🏷️ {summary?.total_labels as number || 0} 个标注</span>
                  <span>📋 {summary?.batches_count as number || 0} 个批次</span>
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="font-semibold text-xs text-gray-500 mb-1">数据包</p>
                        {Object.entries((v.packs || {}) as Record<string, Record<string, number>>).map(([name, info]) => (
                          <div key={name} className="text-xs font-mono text-gray-600">
                            {name}: train={info.train_images} val={info.val_images} test={info.test_images}
                          </div>
                        ))}
                      </div>
                      <div>
                        <p className="font-semibold text-xs text-gray-500 mb-1">批次列表</p>
                        <div className="flex flex-wrap gap-1">
                          {((v.batches || []) as string[]).map((b) => (
                            <Badge key={b} size="small">{b}</Badge>
                          ))}
                        </div>
                        {diff && (
                          <div className="mt-3">
                            <p className="font-semibold text-xs text-gray-500 mb-1">相对父版本变化</p>
                            {((diff.added_packs as string[])?.length > 0) && (
                              <p className="text-xs text-green-600">+ 包: {(diff.added_packs as string[]).join(", ")}</p>
                            )}
                            {((diff.removed_packs as string[])?.length > 0) && (
                              <p className="text-xs text-red-600">- 包: {(diff.removed_packs as string[]).join(", ")}</p>
                            )}
                            {((diff.added_batches as string[])?.length > 0) && (
                              <p className="text-xs text-green-600">+ 批次: {(diff.added_batches as string[]).join(", ")}</p>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 flex gap-2">
                      <Link to="/labeling/catalog" className="text-blue-600 text-xs hover:underline">查看数据目录 →</Link>
                      <Link to="/models/training/records" className="text-blue-600 text-xs hover:underline">查看训练记录 →</Link>
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

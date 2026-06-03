import React, { useEffect, useState, useCallback } from "react";
import { hsapApi } from "@/app/hsap-api";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Userpic } from "@/components/ui/Userpic";
import { PageQueryState } from "@/components/PageQueryState";
import { ListPaginationBar } from "@/components/ListPaginationBar";

type UserRecord = {
  id: number;
  name: string;
  email?: string;
  avatar_url?: string;
  feishu_open_id?: string;
  feishu_union_id?: string;
  feishu_user_id?: string;
  feishu_department_ids?: string[];
  roles: { code: string; name: string }[];
  permissions: string[];
  is_active?: boolean;
};

const ROLE_OPTIONS = [
  { code: "admin", name: "管理员", color: "danger" as const },
  { code: "reviewer", name: "审核员", color: "warning" as const },
  { code: "engineer", name: "工程师", color: "info" as const },
  { code: "labeler", name: "标注员", color: "success" as const },
  { code: "viewer", name: "观察者", color: "default" as const },
];

export const UserManagementPage: React.FC = () => {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (newOffset = 0, newLimit = 20) => {
    setLoading(true);
    setError(null);
    try {
      const res = await hsapApi.listUsers({
        search: search || undefined,
        role: roleFilter || undefined,
        offset: newOffset,
        limit: newLimit,
      });
      setUsers((res.items || []) as unknown as UserRecord[]);
      setTotal(res.total);
      setOffset(newOffset);
      setLimit(newLimit);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [search, roleFilter]);

  useEffect(() => { load(); }, [load]);

  const handleEditRoles = (user: UserRecord) => {
    setEditingUser(user);
    setSelectedRoles(user.roles.map((r) => r.code));
  };

  const handleSaveRoles = async () => {
    if (!editingUser) return;
    setSaving(true);
    try {
      await hsapApi.setUserRoles(editingUser.id, selectedRoles);
      setEditingUser(null);
      load(offset, limit);
    } catch (e) {
      setError(String(e));
    }
    setSaving(false);
  };

  const roleBadge = (code: string) => {
    const opt = ROLE_OPTIONS.find((r) => r.code === code);
    return <Badge key={code} variant={opt?.color || "default"} size="small">{opt?.name || code}</Badge>;
  };

  return (
    <div className="page-container">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>用户管理</h1>
          <p>管理平台用户角色权限，关联飞书账号信息</p>
        </div>
        <Button variant="primary" size="small" onClick={async () => {
          try {
            const res = await hsapApi.syncFeishuUsers();
            alert(`同步完成！共 ${res.total} 人（新增 ${res.created}，更新 ${res.updated}）`);
            load(0, limit);
          } catch (e) { setError(String(e)); }
        }}>
          同步飞书用户
        </Button>
      </div>

      {/* Search & Filter */}
      <div className="flex gap-2 mb-4">
        <input
          className="form-input max-w-xs"
          placeholder="搜索姓名或邮箱..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
        />
        <select className="form-input w-auto" value={roleFilter} onChange={(e) => { setRoleFilter(e.target.value); setOffset(0); }}>
          <option value="">全部角色</option>
          {ROLE_OPTIONS.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
        </select>
      </div>

      <PageQueryState loading={loading} error={error} empty={users.length === 0} emptyMessage="暂无用户">
        <div className="card overflow-hidden">
          <table className="table-auto">
            <thead>
              <tr>
                <th>用户</th>
                <th>邮箱</th>
                <th>飞书 ID</th>
                <th>飞书部门</th>
                <th>角色</th>
                <th>权限数</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div className="flex items-center gap-2">
                      <Userpic username={u.name} avatarUrl={u.avatar_url} size={28} />
                      <span className="font-medium">{u.name}</span>
                    </div>
                  </td>
                  <td className="text-xs text-gray-500">{u.email || "—"}</td>
                  <td className="text-xs font-mono text-gray-400">
                    {u.feishu_user_id ? (
                      <span title={`OpenID: ${u.feishu_open_id || ""} UnionID: ${u.feishu_union_id || ""}`}>
                        {(u.feishu_user_id as string).slice(0, 12)}...
                      </span>
                    ) : (
                      <span className="text-gray-300">非飞书用户</span>
                    )}
                  </td>
                  <td className="text-xs text-gray-500">
                    {u.feishu_department_ids?.length ? `${u.feishu_department_ids.length} 个部门` : "—"}
                  </td>
                  <td>
                    <div className="flex gap-1 flex-wrap">{u.roles.map((r) => roleBadge(r.code))}</div>
                  </td>
                  <td className="text-xs text-gray-500">{u.permissions?.length || 0}</td>
                  <td>
                    <Button size="small" variant="default" onClick={() => handleEditRoles(u)}>编辑角色</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ListPaginationBar total={total} offset={offset} limit={limit}
            onOffsetChange={(o) => load(o, limit)} onLimitChange={(l) => load(0, l)} />
        </div>
      </PageQueryState>

      {/* Role Edit Modal */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setEditingUser(null)}>
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-1">编辑角色 — {editingUser.name}</h3>
            <p className="text-sm text-gray-500 mb-4">{editingUser.email || "—"}</p>

            {editingUser.feishu_open_id && (
              <div className="bg-gray-50 rounded-lg p-3 mb-4 text-xs text-gray-500 space-y-1">
                <p><span className="font-medium">飞书 Open ID:</span> {editingUser.feishu_open_id}</p>
                {editingUser.feishu_union_id && <p><span className="font-medium">Union ID:</span> {editingUser.feishu_union_id}</p>}
                {editingUser.feishu_user_id && <p><span className="font-medium">User ID:</span> {editingUser.feishu_user_id}</p>}
              </div>
            )}

            <div className="space-y-2 mb-4">
              {ROLE_OPTIONS.map((role) => (
                <label key={role.code} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 rounded p-1.5">
                  <input
                    type="checkbox"
                    checked={selectedRoles.includes(role.code)}
                    onChange={(e) => {
                      if (e.target.checked) setSelectedRoles([...selectedRoles, role.code]);
                      else setSelectedRoles(selectedRoles.filter((r) => r !== role.code));
                    }}
                    className="rounded"
                  />
                  <Badge variant={role.color} size="small">{role.name}</Badge>
                  <span className="text-xs text-gray-400">{role.code}</span>
                </label>
              ))}
            </div>

            <div className="flex gap-2 justify-end">
              <Button variant="default" size="small" onClick={() => setEditingUser(null)}>取消</Button>
              <Button variant="primary" size="small" onClick={handleSaveRoles} loading={saving}>保存</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

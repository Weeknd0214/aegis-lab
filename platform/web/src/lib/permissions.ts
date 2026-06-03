// Permission check — matches backend
export function hasPermission(
  user: { permissions: string[] } | null,
  perm: string
): boolean {
  if (!user) return false;
  if (user.permissions.includes("*")) return true;
  return user.permissions.includes(perm);
}

// Permission set — batch check
export function hasAnyPermission(
  user: { permissions: string[] } | null,
  perms: string[]
): boolean {
  return perms.some((p) => hasPermission(user, p));
}

export const PERM_LABELS: Record<string, string> = {
  "*": "全部权限",
  "admin:users": "用户管理",
  "read:pending": "查看待处理",
  "read:catalog": "查看数据目录",
  "read:audit": "查看审核",
  "read:jobs": "查看任务",
  "read:fleet": "查看车队",
  "read:deliveries": "查看批次台账",
  "write:approval_submit": "提交审核",
  "write:approval_review": "审批操作",
  "write:labeling_assign": "分配标注",
  "write:labeling_vendor": "供应商导入",
  "write:fleet": "车队管理",
  "write:delivery_submit": "批次送标",
};

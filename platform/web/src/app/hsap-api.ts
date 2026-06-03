import type { AuthUser, PagedResult, LabelingBatchRow, BatchDelivery } from "@/lib/types";
export type { AuthUser };

const API_BASE = "";

let _token: string | null =
  typeof localStorage !== "undefined"
    ? localStorage.getItem("as_access_token")
    : null;

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (_token) h.Authorization = `Bearer ${_token}`;
  return h;
}

export class HsapApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: { ...authHeaders(), ...((init?.headers as Record<string, string>) || {}) },
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  const text = await res.text();
  if (!res.ok) {
    let detail: unknown;
    try { detail = JSON.parse(text); } catch { /* ignore */ }
    throw new HsapApiError(res.status, text || res.statusText, detail);
  }
  return JSON.parse(text || "{}") as T;
}

async function postJson<T>(url: string, body?: unknown): Promise<T> {
  return fetchJson<T>(url, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
}

async function putJson<T>(url: string, body?: unknown): Promise<T> {
  return fetchJson<T>(url, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined });
}

async function patchJson<T>(url: string, body?: unknown): Promise<T> {
  return fetchJson<T>(url, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined });
}

async function deleteJson<T>(url: string): Promise<T> {
  return fetchJson<T>(url, { method: "DELETE" });
}

export const hsapApi = {
  setToken(token: string | null) {
    _token = token;
    if (token) localStorage.setItem("as_access_token", token);
    else localStorage.removeItem("as_access_token");
  },

  getToken: () => _token,

  authConfig: () =>
    fetchJson<{ feishu_enabled: boolean; dev_auth_enabled: boolean }>(`${API_BASE}/api/v1/auth/config`),

  me: () => fetchJson<AuthUser>(`${API_BASE}/api/v1/auth/me`),

  devLogin: (name?: string) =>
    postJson<{ access_token: string; user: AuthUser }>(`${API_BASE}/api/v1/auth/dev/login`, { name: name || "开发用户" }),

  health: () => fetchJson<{ status: string; database: string }>(`${API_BASE}/api/v1/health`),

  // ── Labeling ──
  labelingBatches: (opts?: { stage?: string; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.stage) p.set("stage", opts.stage);
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    if (opts?.limit != null) p.set("limit", String(opts.limit));
    const q = p.toString();
    return fetchJson<PagedResult<LabelingBatchRow>>(`${API_BASE}/api/v1/labeling/batches${q ? `?${q}` : ""}`);
  },

  openLabelingCampaign: (body: { project: string; task: string; batch: string; mode?: string | null; pack?: string | null; location?: string }) =>
    postJson(`${API_BASE}/api/v1/labeling/campaigns/open`, body),

  labelingAssignees: () =>
    fetchJson<{ items: { id: number; name: string; roles: string[] }[] }>(`${API_BASE}/api/v1/labeling/assignees`),

  assignLabelingCampaign: (campaignId: string, userId: number | null) =>
    patchJson(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/assign`, { user_id: userId }),

  getLabelingCampaign: (id: string) =>
    fetchJson<LabelingBatchRow & { config_xml?: string }>(`${API_BASE}/api/v1/labeling/campaigns/${id}`),

  labelingBootstrap: (campaignId: string) =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/bootstrap`),

  campaignProgress: (campaignId: string) =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/progress`),

  labelingTasks: (campaignId: string, offset = 0, limit = 50, opts?: { assignee?: "me" | "all" }) => {
    const capped = Math.min(Math.max(1, limit), 100);
    const q = new URLSearchParams({ offset: String(offset), limit: String(capped) });
    if (opts?.assignee === "me") q.set("assignee", "me");
    if (opts?.assignee === "all") q.set("assignee", "all");
    return fetchJson<{ tasks: { id: string; data: { image: string } }[]; total: number; hint?: string; my_assigned?: number }>(
      `${API_BASE}/api/v1/labeling/campaigns/${campaignId}/tasks?${q}`,
    );
  },

  getAnnotation: (campaignId: string, taskId: string) =>
    fetchJson<{ task_id: string; result?: unknown }>(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/annotations/${taskId}`),

  saveAnnotation: (campaignId: string, taskId: string, body: { result?: unknown; annotations?: unknown[] }) =>
    putJson(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/annotations/${taskId}`, body),

  labelingExport: (campaignId: string) =>
    postJson<{ ok: boolean; job?: { id: string } }>(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/export`),

  submitLabelingCampaign: (campaignId: string) =>
    postJson<Record<string, unknown>>(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/submit`),

  importVendorZip: (campaignId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const h: Record<string, string> = {};
    if (_token) h.Authorization = `Bearer ${_token}`;
    return fetch(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/import-vendor`, {
      method: "POST", headers: h, body: form,
    }).then(async (res) => {
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    });
  },

  listCampaignExportJobs: (campaignId: string, limit = 20) =>
    fetchJson<{ items: Record<string, unknown>[] }>(`${API_BASE}/api/v1/labeling/campaigns/${campaignId}/export-jobs?limit=${limit}`),

  labelingRegistryProfiles: () =>
    fetchJson<{ profiles: Record<string, unknown>[] }>(`${API_BASE}/api/v1/labeling/registry-profiles`),

  labelingAcquireLock: (campaignId: string, taskId: string) =>
    postJson<{ ok: boolean; holder?: string }>(
      `${API_BASE}/api/v1/labeling/campaigns/${campaignId}/tasks/${encodeURIComponent(taskId)}/lock`,
    ),

  labelingReleaseLock: (campaignId: string, taskId: string) =>
    deleteJson<{ ok: boolean }>(
      `${API_BASE}/api/v1/labeling/campaigns/${campaignId}/tasks/${encodeURIComponent(taskId)}/lock`,
    ),

  labelingReleaseLockKeepalive(campaignId: string, taskId: string) {
    const url = `${API_BASE}/api/v1/labeling/campaigns/${campaignId}/tasks/${encodeURIComponent(taskId)}/lock`;
    fetch(url, { method: "DELETE", headers: authHeaders(), keepalive: true }).catch(() => {});
  },

  labelingRenewLock: (campaignId: string, taskId: string) =>
    postJson<{ ok: boolean }>(
      `${API_BASE}/api/v1/labeling/campaigns/${campaignId}/tasks/${encodeURIComponent(taskId)}/lock/renew`,
    ),

  labelingTasksPageLimit: 100,

  async labelingTasksAll(
    campaignId: string,
    opts?: { assignee?: "me" | "all" },
  ): Promise<{ tasks: { id: string; data: { image: string } }[]; total: number; hint?: string; my_assigned?: number }> {
    const page = 100;
    let offset = 0;
    let total = 0;
    let hint: string | undefined;
    let myAssigned: number | undefined;
    const tasks: { id: string; data: { image: string } }[] = [];
    for (;;) {
      const res = await this.labelingTasks(campaignId, offset, page, opts);
      tasks.push(...(res.tasks || []));
      total = res.total;
      hint = res.hint ?? hint;
      myAssigned = res.my_assigned ?? myAssigned;
      offset += page;
      if (tasks.length >= total || !(res.tasks?.length)) break;
    }
    return { tasks, total, hint, my_assigned: myAssigned };
  },

  // ── Pending / Catalog ──
  pending: () => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/pending`),
  pendingGates: () => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/pending/gates`),
  catalog: (refresh = false) => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/catalog${refresh ? "?refresh=true" : ""}`),
  catalogDms: (task: string, refresh = false) =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/catalog/dms/${encodeURIComponent(task)}${refresh ? "?refresh=true" : ""}`),

  // ── Data upload ──
  uploadDatasetFile: (file: File, project: string, task?: string, mode?: string, onProgress?: (n: number) => void) => {
    const formData = new FormData();
    formData.append("project", project);
    if (task) formData.append("task", task);
    if (mode) formData.append("mode", mode);
    formData.append("file", file);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/v1/data/upload/file`, true);
      if (_token) xhr.setRequestHeader("Authorization", `Bearer ${_token}`);
      xhr.upload.onprogress = (evt) => {
        if (!onProgress || !evt.lengthComputable) return;
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      };
      xhr.onerror = () => reject(new Error("上传失败"));
      xhr.onload = () => {
        if (xhr.status === 401) return reject(new Error("UNAUTHORIZED"));
        if (xhr.status < 200 || xhr.status >= 300) return reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
        try { resolve(JSON.parse(xhr.responseText || "{}")); } catch { reject(new Error("上传响应解析失败")); }
      };
      xhr.send(formData);
    });
  },

  listDataCandidates: (opts?: { offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    p.set("limit", String(opts?.limit ?? 20));
    return fetchJson<PagedResult<Record<string, unknown>>>(`${API_BASE}/api/v1/data/candidates?${p}`);
  },

  promoteCandidateInbox: (candidateId: string, body?: { batch?: string; mode?: string }) =>
    postJson<{ ok: boolean; inbox_path?: string }>(`${API_BASE}/api/v1/data/candidates/${encodeURIComponent(candidateId)}/promote-inbox`, body || {}),

  registryTasks: (project = "dms") =>
    fetchJson<{ project: string; tasks: Record<string, unknown> }>(`${API_BASE}/api/v1/data/registry-tasks?project=${encodeURIComponent(project)}`),

  scanInbox: (project = "dms") =>
    fetchJson<{ project: string; items: Record<string, unknown>[]; inbox_path: string }>(`${API_BASE}/api/v1/data/scan-inbox?project=${encodeURIComponent(project)}`),

  registerBatch: (body: Record<string, unknown>) => postJson(`${API_BASE}/api/v1/register-batch`, body),

  // ── Deliveries ──
  listDeliveries: (opts?: { status?: string; mine?: boolean; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.status) p.set("status", opts.status);
    if (opts?.mine) p.set("mine", "1");
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    if (opts?.limit != null) p.set("limit", String(opts.limit));
    return fetchJson<PagedResult<BatchDelivery>>(`${API_BASE}/api/v1/deliveries?${p}`);
  },

  getDelivery: (id: string) => fetchJson<BatchDelivery>(`${API_BASE}/api/v1/deliveries/${encodeURIComponent(id)}`),

  createDelivery: (body: Record<string, unknown>) => postJson<BatchDelivery>(`${API_BASE}/api/v1/deliveries`, body),

  patchDelivery: (id: string, body: Record<string, unknown>) =>
    patchJson<BatchDelivery>(`${API_BASE}/api/v1/deliveries/${encodeURIComponent(id)}`, body),

  submitDelivery: (id: string) =>
    postJson<BatchDelivery>(`${API_BASE}/api/v1/deliveries/${encodeURIComponent(id)}/submit`),

  deleteDelivery: (id: string) => deleteJson<{ ok: boolean }>(`${API_BASE}/api/v1/deliveries/${encodeURIComponent(id)}`),

  retryDeliveryIngest: (id: string) =>
    postJson<{ ok: boolean; job_id?: string }>(`${API_BASE}/api/v1/deliveries/${encodeURIComponent(id)}/retry-ingest`),

  // ── Audit ──
  listActions: () => fetchJson<{ actions: { id: string; label: string }[] }>(`${API_BASE}/api/v1/actions`),

  listApprovals: (opts?: { status?: string; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.status) p.set("status", opts.status);
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    if (opts?.limit != null) p.set("limit", String(opts.limit));
    return fetchJson<PagedResult<Record<string, unknown>>>(`${API_BASE}/api/v1/approvals?${p}`);
  },

  getApproval: (id: string) => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/approvals/${id}`),
  getApprovalPreview: (id: string) => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/approvals/${id}/preview`),

  listApprovalImages: (id: string, offset = 0, limit = 60) =>
    fetchJson<{ total: number; items: { id: string }[] }>(`${API_BASE}/api/v1/approvals/${id}/images?offset=${offset}&limit=${limit}`),

  fetchApprovalImageBlob: async (approvalId: string, imageId: string, thumb = true) => {
    const q = thumb ? "?thumb=true" : "?thumb=false";
    const res = await fetch(`${API_BASE}/api/v1/approvals/${approvalId}/images/${imageId}${q}`, { headers: authHeaders(), cache: "no-store" });
    if (!res.ok) throw new Error(await res.text());
    return URL.createObjectURL(await res.blob());
  },

  approvalRejectionCategories: () =>
    fetchJson<{ categories: { key: string; label: string }[] }>(`${API_BASE}/api/v1/system/audit/rejection-categories`),

  approve: (id: string, comment?: string) => postJson(`${API_BASE}/api/v1/system/audit/${id}/approve`, { comment }),
  reject: (id: string, comment?: string, rejectionCategory?: string) =>
    postJson(`${API_BASE}/api/v1/system/audit/${id}/reject`, { comment, rejection_category: rejectionCategory || "" }),

  batchApprove: (ids: string[]) =>
    postJson(`${API_BASE}/api/v1/system/audit/batch-approve`, { ids }),
  batchReject: (ids: string[], comment?: string, rejectionCategory?: string) =>
    postJson(`${API_BASE}/api/v1/system/audit/batch-reject`, { ids, comment, rejection_category: rejectionCategory || "" }),
  submitApproval: (action: string, params: Record<string, unknown>, note?: string) =>
    postJson(`${API_BASE}/api/v1/system/audit/submit`, { action, params, note }),
  submitBuildBatch: (body: Record<string, unknown>) => postJson(`${API_BASE}/api/v1/system/audit/submit-build-batch`, body),

  // ── Jobs ──
  listJobs: (opts?: { status?: string; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.status) p.set("status", opts.status);
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    if (opts?.limit != null) p.set("limit", String(opts.limit));
    return fetchJson<PagedResult<Record<string, unknown>>>(`${API_BASE}/api/v1/jobs?${p}`).catch(() => ({ items: [], total: 0 }));
  },

  getJob: (id: string) => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/jobs/${id}`),

  // ── Training / Models ──
  listTrainingRecords: (opts?: { project?: string; status?: string; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.project) p.set("project", opts.project);
    if (opts?.status) p.set("status", opts.status);
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    if (opts?.limit != null) p.set("limit", String(opts.limit));
    const q = p.toString();
    return fetchJson<PagedResult<Record<string, unknown>>>(`${API_BASE}/api/v1/models/records${q ? `?${q}` : ""}`);
  },

  getTrainingRecord: (jobId: string) =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/models/records/${encodeURIComponent(jobId)}`),

  getModelRegistry: (project = "dms", task?: string) => {
    const p = new URLSearchParams({ project });
    if (task) p.set("task", task);
    return fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/models/registry?${p}`);
  },

  createTrainingRecord: (action: string, params: Record<string, unknown>, note?: string) =>
    postJson(`${API_BASE}/api/v1/models/records`, { action, params, note }),

  trainingActions: () =>
    fetchJson<{ actions: { id: string; label: string }[] }>(`${API_BASE}/api/v1/models/actions`),

  // ── Fleet ──
  fleetMapConfig: () => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/fleet/map-config`),
  fleetLive: () => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/fleet/live`),
  fleetSummary: () => fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/fleet/summary`),
  fleetVehicles: () => fetchJson<{ items: Record<string, unknown>[] }>(`${API_BASE}/api/v1/fleet/vehicles`),

  fleetCreateVehicle: (body: { plate_no: string; tbox_device_id: string; name?: string; team?: string }) =>
    postJson(`${API_BASE}/api/v1/fleet/vehicles`, body),

  fleetUpdateVehicle: (id: number, body: Record<string, unknown>) =>
    patchJson(`${API_BASE}/api/v1/fleet/vehicles/${id}`, body),

  fleetDeleteVehicle: (id: number) => deleteJson(`${API_BASE}/api/v1/fleet/vehicles/${id}`),

  fleetRuns: (opts?: { vehicle_id?: number; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.vehicle_id != null) p.set("vehicle_id", String(opts.vehicle_id));
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    if (opts?.limit != null) p.set("limit", String(opts.limit));
    return fetchJson<PagedResult<Record<string, unknown>>>(`${API_BASE}/api/v1/fleet/runs?${p}`);
  },

  fleetRunDetail: (runId: number) =>
    fetchJson<{ run: Record<string, unknown>; vehicle: Record<string, unknown> | null; milestones: Record<string, unknown>[] }>(
      `${API_BASE}/api/v1/fleet/runs/${runId}`),

  fleetRunTrack: (runId: number) =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/fleet/runs/${runId}/track`),

  fleetImportGpx: (vehicleId: number, file: File, note?: string) => {
    const form = new FormData();
    form.append("vehicle_id", String(vehicleId));
    form.append("file", file);
    if (note) form.append("note", note);
    const h: Record<string, string> = {};
    if (_token) h.Authorization = `Bearer ${_token}`;
    return fetch(`${API_BASE}/api/v1/fleet/runs/import-gpx`, { method: "POST", headers: h, body: form })
      .then(async (res) => { if (!res.ok) throw new Error(await res.text()); return res.json(); });
  },

  fleetImportCsv: (vehicleId: number, file: File, opts?: { note?: string; project?: string; batch?: string }) => {
    const form = new FormData();
    form.append("vehicle_id", String(vehicleId));
    form.append("file", file);
    if (opts?.note) form.append("note", opts.note);
    if (opts?.project) form.append("project", opts.project);
    if (opts?.batch) form.append("batch", opts.batch);
    const h: Record<string, string> = {};
    if (_token) h.Authorization = `Bearer ${_token}`;
    return fetch(`${API_BASE}/api/v1/fleet/runs/import-csv`, { method: "POST", headers: h, body: form })
      .then(async (res) => { if (!res.ok) throw new Error(await res.text()); return res.json(); });
  },

  fleetReseedDemo: () => postJson(`${API_BASE}/api/v1/fleet/mock/reseed`),

  // ── Traces / Agents ──
  listTraces: (limit = 50) =>
    fetchJson<{ trace_ids: string[] }>(`${API_BASE}/api/v1/traces?limit=${limit}`),

  getTrace: (traceId: string) =>
    fetchJson<{ trace_id: string; spans: Record<string, unknown>[] }>(`${API_BASE}/api/v1/traces/${traceId}`),

  listTools: () =>
    fetchJson<{ tools: string[] }>(`${API_BASE}/api/v1/agents/tools`),

  invokeAgent: (graph: string, params: Record<string, unknown>) =>
    postJson(`${API_BASE}/api/v1/agents/invoke`, { graph, params }),

  // ── User management ──
  listUsers: (opts?: { search?: string; role?: string; offset?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (opts?.search) p.set("search", opts.search);
    if (opts?.role) p.set("role", opts.role);
    if (opts?.offset != null) p.set("offset", String(opts.offset));
    p.set("limit", String(opts?.limit ?? 20));
    const q = p.toString();
    return fetchJson<{ items: Record<string, unknown>[]; total: number }>(`${API_BASE}/api/v1/auth/users${q ? `?${q}` : ""}`);
  },

  setUserRoles: (userId: number, roles: string[]) =>
    putJson(`${API_BASE}/api/v1/auth/users/${userId}/roles`, { roles }),

  syncFeishuUsers: () =>
    postJson<{ ok: boolean; created: number; updated: number; total: number }>(`${API_BASE}/api/v1/system/feishu/sync-users`),

  // ── Dataset Versions ──
  listDatasetVersions: (project = "dms") =>
    fetchJson<{ items: Record<string, unknown>[] }>(`${API_BASE}/api/v1/models/datasets?project=${encodeURIComponent(project)}`),

  createDatasetSnapshot: (project: string, description: string) =>
    postJson<Record<string, unknown>>(`${API_BASE}/api/v1/models/datasets/snapshot`, { project, description }),

  getDatasetVersion: (versionId: string, project = "dms") =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/models/datasets/${encodeURIComponent(versionId)}?project=${encodeURIComponent(project)}`),

  diffDatasetVersions: (v1: string, v2: string, project = "dms") =>
    fetchJson<Record<string, unknown>>(`${API_BASE}/api/v1/models/datasets/${encodeURIComponent(v2)}/diff?compare=${encodeURIComponent(v1)}&project=${encodeURIComponent(project)}`),
};

export function mediaUrl(path: string): string {
  if (path.startsWith("http") || path.startsWith("/api/")) {
    return path.startsWith("http") ? path : `${API_BASE || ""}${path}`;
  }
  return path;
}

export async function fetchLabelingMediaBlob(imageApiPath: string): Promise<string> {
  const url = mediaUrl(imageApiPath);
  const res = await fetch(url, { headers: authHeaders(), cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return URL.createObjectURL(await res.blob());
}

export function formatLockConflict(err: unknown): string {
  if (err instanceof HsapApiError && err.status === 409) {
    const raw = err.detail as Record<string, unknown> | undefined;
    const inner = (raw?.detail as Record<string, unknown> | undefined) ?? raw;
    const holder = inner?.holder as string | undefined;
    return holder ? `该图正由 ${holder} 标注中` : "该图片正被其他用户标注";
  }
  return String(err);
}

export function hasPermission(user: { permissions: string[] } | null, perm: string): boolean {
  if (!user) return false;
  if (user.permissions.includes("*")) return true;
  return user.permissions.includes(perm);
}

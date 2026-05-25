const API_BASE = import.meta.env.VITE_API_BASE || "";

let _token: string | null = localStorage.getItem("as_access_token");

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (_token) h.Authorization = `Bearer ${_token}`;
  return h;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: { ...authHeaders(), ...(init?.headers as Record<string, string>) },
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(await res.text() || res.statusText);
  return (await res.json()) as T;
}

async function postJson<T = unknown>(url: string, body?: unknown): Promise<T> {
  return fetchJson<T>(url, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

function uploadWithProgress(
  url: string,
  formData: FormData,
  onProgress?: (percent: number) => void
): Promise<{ candidate: DataCandidate; job: JobRecord }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    if (_token) xhr.setRequestHeader("Authorization", `Bearer ${_token}`);
    xhr.upload.onprogress = (evt) => {
      if (!onProgress || !evt.lengthComputable) return;
      const pct = Math.round((evt.loaded / evt.total) * 100);
      onProgress(pct);
    };
    xhr.onerror = () => reject(new Error("上传失败"));
    xhr.onload = () => {
      if (xhr.status === 401) return reject(new Error("UNAUTHORIZED"));
      if (xhr.status < 200 || xhr.status >= 300) return reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
      try {
        const parsed = JSON.parse(xhr.responseText || "{}");
        resolve(parsed);
      } catch (e) {
        reject(new Error("上传响应解析失败"));
      }
    };
    xhr.send(formData);
  });
}

export type AuthUser = {
  id: number;
  name: string;
  email?: string;
  avatar_url?: string;
  roles: { code: string; name: string }[];
  permissions: string[];
};

export const api = {
  base: API_BASE || window.location.origin,

  setToken(token: string | null) {
    _token = token;
  },

  authConfig: () => fetchJson<{ feishu_enabled: boolean; dev_auth_enabled: boolean }>(`${API_BASE}/api/v1/auth/config`),

  me: () => fetchJson<AuthUser>(`${API_BASE}/api/v1/auth/me`),

  devLogin: (name?: string) => postJson<{ access_token: string; user: AuthUser }>(`${API_BASE}/api/v1/auth/dev/login`, { name: name || "开发用户" }),

  health: () =>
    fetchJson<{
      status: string;
      workspace?: string;
      database?: string;
      db_connected?: string;
      redis_connected?: string;
    }>(`${API_BASE}/api/v1/health`),

  pending: () => fetchJson<PendingReport>(`${API_BASE}/api/v1/pending`),

  catalog: (refresh = false) =>
    fetchJson<CatalogReport>(`${API_BASE}/api/v1/catalog${refresh ? "?refresh=true" : ""}`),

  listApprovals: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return fetchJson<{ items: ApprovalRecord[] }>(`${API_BASE}/api/v1/approvals${q}`);
  },

  getApproval: (id: string) => fetchJson<ApprovalRecord>(`${API_BASE}/api/v1/approvals/${encodeURIComponent(id)}`),

  getApprovalPreview: (id: string) =>
    fetchJson<AuditPreview>(`${API_BASE}/api/v1/approvals/${encodeURIComponent(id)}/preview`),

  listApprovalImages: (id: string, offset = 0, limit = 60) =>
    fetchJson<{ total: number; offset: number; limit: number; items: AuditImageItem[] }>(
      `${API_BASE}/api/v1/approvals/${encodeURIComponent(id)}/images?offset=${offset}&limit=${limit}`
    ),

  fetchApprovalImageBlob: async (approvalId: string, imageId: string, thumb = true): Promise<string> => {
    const q = thumb ? "?thumb=true" : "?thumb=false";
    const res = await fetch(
      `${API_BASE}/api/v1/approvals/${encodeURIComponent(approvalId)}/images/${encodeURIComponent(imageId)}${q}`,
      { headers: authHeaders(), cache: "no-store" }
    );
    if (!res.ok) throw new Error(await res.text() || res.statusText);
    return URL.createObjectURL(await res.blob());
  },

  submitApproval: (action: string, params: Record<string, unknown>, note?: string) =>
    postJson(`${API_BASE}/api/v1/approvals/submit`, { action, params, note }),

  submitBuildBatch: (body: Record<string, unknown>) =>
    postJson(`${API_BASE}/api/v1/approvals/submit-build-batch`, body),

  approve: (id: string, comment?: string) =>
    postJson(`${API_BASE}/api/v1/approvals/${id}/approve`, { comment }),

  reject: (id: string, comment?: string) =>
    postJson(`${API_BASE}/api/v1/approvals/${id}/reject`, { comment }),

  registerBatch: (body: Record<string, unknown>) =>
    postJson(`${API_BASE}/api/v1/register-batch`, body),

  listJobs: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    return fetchJson<{ items: JobRecord[] }>(`${API_BASE}/api/v1/jobs${q}`).catch(() => ({ items: [] }));
  },

  listTrainingRecords: (opts?: {
    project?: string;
    kind?: string;
    status?: string;
    task?: string;
    limit?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.project) params.set("project", opts.project);
    if (opts?.kind) params.set("kind", opts.kind);
    if (opts?.status) params.set("status", opts.status);
    if (opts?.task) params.set("task", opts.task);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const q = params.toString();
    return fetchJson<{ items: TrainingRecord[]; total: number; summary: TrainingSummary }>(
      `${API_BASE}/api/v1/training/records${q ? `?${q}` : ""}`
    );
  },

  getTrainingRecord: (jobId: string) =>
    fetchJson<TrainingRecord>(`${API_BASE}/api/v1/training/records/${encodeURIComponent(jobId)}`),

  getModelRegistry: (project = "dms", task?: string) => {
    const params = new URLSearchParams({ project });
    if (task) params.set("task", task);
    return fetchJson<ModelRegistry>(`${API_BASE}/api/v1/training/models?${params.toString()}`);
  },

  createTrainingRecord: (action: string, params: Record<string, unknown>, note?: string) =>
    postJson<ApprovalRecord>(`${API_BASE}/api/v1/training/records`, { action, params, note }),

  uploadDatasetFile: (
    file: File,
    project: string,
    task?: string,
    onProgress?: (percent: number) => void
  ) => {
    const formData = new FormData();
    formData.append("project", project);
    if (task) formData.append("task", task);
    formData.append("file", file);
    return uploadWithProgress(`${API_BASE}/api/v1/data/upload/file`, formData, onProgress);
  },

  listDataCandidates: (limit = 50) =>
    fetchJson<{ items: DataCandidate[] }>(`${API_BASE}/api/v1/data/candidates?limit=${limit}`),

  getDataCandidate: (candidateId: string) =>
    fetchJson<DataCandidate>(`${API_BASE}/api/v1/data/candidates/${encodeURIComponent(candidateId)}`),

  inspectUploadPath: (project: "dms" | "lane", sourcePath: string, task?: string) =>
    postJson<InspectUploadResponse>(`${API_BASE}/api/v1/data/inspect-upload`, {
      project,
      task: task || undefined,
      source_path: sourcePath,
    }),
};

export type BatchRecord = {
  project: string;
  task?: string;
  batch: string;
  pack?: string;
  stage: string;
  location: string;
  path?: string;
  counts?: { images?: number; labels?: number };
  engineer?: string;
  format?: string;
  next_cli?: string;
};

export type PendingReport = {
  workspace: string;
  batches: BatchRecord[];
  projects?: {
    dms?: {
      active_packs?: string[];
      not_enabled?: string[];
      task_defs?: Record<string, { type: string; nc?: number }>;
      tasks?: Record<string, { inbox?: unknown[]; sources?: Record<string, unknown[]> }>;
      recent_ingest?: { task: string; pack?: string; ts?: string; added?: number }[];
    };
    lane?: { packs?: Record<string, { path: string; train_lines?: number; enabled?: boolean }> };
  };
};

export type CatalogReport = {
  _cache?: {
    cached?: boolean;
    cache_source?: string;
    cache_age_sec?: number;
    build_source?: string;
  };
  dms?: Record<string, {
    type: string;
    nc?: number;
    class_counts?: Record<string, number>;
    packs?: {
      name: string;
      enabled: boolean;
      train_images?: number;
      val_images?: number;
      test_images?: number;
      class_counts?: Record<string, number>;
      label_files?: number;
      total_boxes?: number;
      sampled?: boolean;
      bbox_points?: [number, number][];
      path?: string;
      role?: string;
      frozen?: boolean;
    }[];
    drop_paths?: { inbox?: string };
  }>;
  lane?: Record<string, {
    path?: string;
    drop_path?: string;
    train_lines?: number;
    val_lines?: number;
    test_lines?: number;
    enabled?: boolean;
    add_template?: string;
    quality?: {
      analyzed_frames?: number;
      lane_count_hist?: Record<string, number>;
      length_hist?: { left: number; right: number; count: number }[];
      curvature_hist?: { left: number; right: number; count: number }[];
    };
  }>;
};

export type ApprovalRecord = {
  id: string;
  action: string;
  action_label?: string;
  status: string;
  params?: Record<string, unknown>;
  note?: string | null;
  submitted_by?: string;
  submitted_at?: string;
  review_comment?: string;
  result?: { error?: string; ok?: boolean };
};

export type AuditImageItem = {
  id: string;
  batch: string;
  location: string;
  split: string;
  filename: string;
  has_label: boolean;
  box_count: number;
  missing_label: boolean;
};

export type AuditPreview = {
  approval: ApprovalRecord;
  scope_label?: string;
  task?: string;
  pack?: string;
  class_names?: Record<number, string>;
  batches?: { batch?: string; location?: string; path?: string; exists?: boolean }[];
};

export type JobRecord = {
  id: string;
  action: string;
  status: string;
  approval_id?: string;
  params?: Record<string, unknown>;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  result?: { error?: string; ok?: boolean; [key: string]: unknown };
};

export type TrainingSummary = {
  total: number;
  running: number;
  queued: number;
  succeeded: number;
  failed: number;
};

export type TrainingRecord = JobRecord & {
  action_label?: string;
  project?: string;
  kind?: string;
  task?: string | null;
  track?: string;
  weight_path?: string | null;
  metrics?: Record<string, unknown>;
  error?: string | null;
  duration_sec?: number | null;
  approval?: ApprovalRecord | null;
};

export type ModelRegistry = {
  project: string;
  task?: string;
  version?: Record<string, unknown>;
  tasks?: Record<string, Record<string, unknown>>;
  eval_history?: Record<string, unknown>[];
};

export type DataCandidate = {
  id: string;
  project: string;
  task?: string;
  status: string;
  source_type: string;
  original_name?: string;
  upload_path: string;
  analyzed_source_path?: string;
  format_id?: string;
  split_counts?: Record<string, number>;
  error_message?: string;
  upload_size_bytes?: number;
  submitted_by_name?: string;
  analysis_job_id?: string;
  created_at?: string;
  updated_at?: string;
};

export type InspectUploadResponse = {
  ok: boolean;
  normalized: {
    format_id: string;
    project: string;
    task?: string;
    source_path: string;
    split_counts?: Record<string, number>;
    sample_count?: number;
    annotation_count?: number;
    artifacts?: string[];
    warnings?: string[];
    extra?: Record<string, unknown>;
  };
};

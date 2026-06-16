// Shared type definitions

export type AuthUser = {
  id: number;
  name: string;
  email?: string;
  avatar_url?: string;
  roles: { code: string; name: string }[];
  permissions: string[];
};

export type PagedResult<T> = {
  items: T[];
  total: number;
  offset?: number;
  limit?: number;
};

export type BatchRecord = {
  project: string;
  task?: string;
  mode?: string;
  batch: string;
  pack?: string;
  stage: string;
  location: string;
  path?: string;
  counts?: { images?: number; labels?: number };
  next_cli?: string;
};

export type LabelingBatchRow = BatchRecord & {
  scope_key?: string;
  domain?: string;
  domain_label?: string;
  task_label?: string;
  mode_label?: string;
  labeling_profile?: string;
  export_default?: string;
  ml_adapter?: string;
  campaign_id?: string;
  campaign_status?: string;
  assigned_to_user_id?: number | null;
  assigned_to_name?: string | null;
  total_tasks?: number;
  completed_tasks?: number;
  assigned_tasks?: number;
};

export type BatchDelivery = {
  id: string;
  project: string;
  task?: string | null;
  mode?: string | null;
  batch_name: string;
  source_type?: string | null;
  vehicle_scene?: string | null;
  collection_start?: string | null;
  collection_end?: string | null;
  data_path: string;
  estimated_count?: number | null;
  remark?: string | null;
  status: string;
  owner_user_id?: number | null;
  owner_name?: string | null;
  submitted_by_user_id?: number | null;
  submitted_by_name?: string | null;
  approval_id?: string | null;
  approval_status?: string | null;
  job_id?: string | null;
  job_status?: string | null;
  candidate_id?: string | null;
  inbox_path?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type JobRecord = {
  id: string;
  action: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  result?: unknown;
  error?: string;
};

export type ApprovalRecord = {
  id: string;
  action: string;
  action_label?: string;
  status: string;
  params?: Record<string, unknown>;
  submitted_by_name?: string | null;
  submitted_by?: string;
  reviewed_by?: string;
  note?: string;
  comment?: string;
  created_at?: string;
};

export type FleetVehicle = {
  id: number;
  plate_no: string;
  tbox_device_id: string;
  name?: string;
  team?: string;
  status: string;
};

export type FleetRun = {
  id: number;
  vehicle_id: number;
  status: string;
  started_at?: string;
  ended_at?: string;
};

export type ModelRecord = {
  id: string;
  project: string;
  task?: string;
  version?: string;
  metrics?: Record<string, number>;
  status: string;
  created_at?: string;
};

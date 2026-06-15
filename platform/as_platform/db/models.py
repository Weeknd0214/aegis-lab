"""ORM 模型。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from as_platform.db.engine import Base

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    feishu_open_id = Column(String(64), unique=True, nullable=True, index=True)
    feishu_union_id = Column(String(64), unique=True, nullable=True, index=True)
    feishu_user_id = Column(String(64), unique=True, nullable=True, index=True)
    feishu_tenant_key = Column(String(128), nullable=True)
    feishu_department_ids_json = Column(Text, nullable=True)
    name = Column(String(128), nullable=False, default="")
    email = Column(String(256), nullable=True)
    avatar_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    roles = relationship("Role", secondary=user_roles, back_populates="users")

    def feishu_department_ids(self) -> list[str]:
        if not self.feishu_department_ids_json:
            return []
        try:
            data = json.loads(self.feishu_department_ids_json)
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:
            return []
        return []


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)

    users = relationship("User", secondary=user_roles, back_populates="roles")
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(128), nullable=False)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String(64), primary_key=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    action = Column(String(64), nullable=False)
    action_label = Column(String(128), nullable=True)
    params_json = Column(Text, nullable=False, default="{}")
    note = Column(Text, nullable=True)
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_by_name = Column(String(128), nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=_utcnow)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_name = Column(String(128), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)
    rejection_category = Column(String(32), nullable=True, default="")
    job_id = Column(String(64), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    result_json = Column(Text, nullable=True)

    def params(self) -> dict:
        return json.loads(self.params_json or "{}")

    def set_params(self, data: dict) -> None:
        self.params_json = json.dumps(data, ensure_ascii=False)

    def result(self) -> dict | None:
        if not self.result_json:
            return None
        return json.loads(self.result_json)

    def set_result(self, data: dict) -> None:
        self.result_json = json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "action": self.action,
            "action_label": self.action_label,
            "params": self.params(),
            "note": self.note,
            "submitted_by": self.submitted_by_name,
            "submitted_by_user_id": self.submitted_by_user_id,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "reviewed_by": self.reviewed_by_name,
            "reviewed_by_user_id": self.reviewed_by_user_id,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "review_comment": self.review_comment,
            "rejection_category": self.rejection_category or "",
            "job_id": self.job_id,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "result": self.result(),
        }


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    action = Column(String(64), nullable=False)
    params_json = Column(Text, nullable=False, default="{}")
    approval_id = Column(String(64), ForeignKey("approvals.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    result_json = Column(Text, nullable=True)

    def params(self) -> dict:
        return json.loads(self.params_json or "{}")

    def set_params(self, data: dict) -> None:
        self.params_json = json.dumps(data, ensure_ascii=False)

    def result(self) -> dict | None:
        if not self.result_json:
            return None
        return json.loads(self.result_json)

    def set_result(self, data: dict) -> None:
        self.result_json = json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "action": self.action,
            "params": self.params(),
            "approval_id": self.approval_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result(),
        }


class DatasetCandidate(Base):
    __tablename__ = "dataset_candidates"

    id = Column(String(64), primary_key=True)
    project = Column(String(32), nullable=False, index=True)
    task = Column(String(64), nullable=True, index=True)
    mode = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="uploaded", index=True)
    source_type = Column(String(32), nullable=False, default="upload")
    original_name = Column(String(255), nullable=True)
    upload_path = Column(String(1024), nullable=False)
    analyzed_source_path = Column(String(1024), nullable=True)
    format_id = Column(String(64), nullable=True)
    split_counts_json = Column(Text, nullable=False, default="{}")
    quality_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    upload_size_bytes = Column(Integer, nullable=False, default=0)
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_by_name = Column(String(128), nullable=True)
    analysis_job_id = Column(String(64), ForeignKey("jobs.id"), nullable=True)
    inbox_path = Column(String(1024), nullable=True)
    promoted_batch = Column(String(128), nullable=True)
    external_id = Column(String(128), nullable=True, index=True)
    feishu_record_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def split_counts(self) -> dict:
        return json.loads(self.split_counts_json or "{}")

    def set_split_counts(self, data: dict) -> None:
        self.split_counts_json = json.dumps(data, ensure_ascii=False)

    def quality(self) -> dict | None:
        if not self.quality_json:
            return None
        return json.loads(self.quality_json)

    def set_quality(self, data: dict) -> None:
        self.quality_json = json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "task": self.task,
            "mode": self.mode,
            "status": self.status,
            "source_type": self.source_type,
            "original_name": self.original_name,
            "upload_path": self.upload_path,
            "analyzed_source_path": self.analyzed_source_path,
            "format_id": self.format_id,
            "split_counts": self.split_counts(),
            "quality": self.quality(),
            "error_message": self.error_message,
            "upload_size_bytes": self.upload_size_bytes,
            "submitted_by_user_id": self.submitted_by_user_id,
            "submitted_by_name": self.submitted_by_name,
            "analysis_job_id": self.analysis_job_id,
            "inbox_path": self.inbox_path,
            "promoted_batch": self.promoted_batch,
            "external_id": self.external_id,
            "feishu_record_id": self.feishu_record_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BatchDelivery(Base):
    """平台内数据送标申请（替代飞书多维表格拉取）。"""

    __tablename__ = "batch_deliveries"
    __table_args__ = (
        UniqueConstraint("project", "task", "mode", "batch_name", name="uq_batch_deliveries_batch"),
    )

    id = Column(String(64), primary_key=True)
    project = Column(String(32), nullable=False, index=True)
    task = Column(String(64), nullable=True, index=True)
    mode = Column(String(64), nullable=True)
    batch_name = Column(String(128), nullable=False, index=True)
    source_type = Column(String(64), nullable=True)
    vehicle_scene = Column(String(256), nullable=True)
    collection_start = Column(String(32), nullable=True)
    collection_end = Column(String(32), nullable=True)
    data_path = Column(String(1024), nullable=False)
    estimated_count = Column(Integer, nullable=True)
    remark = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner_name = Column(String(128), nullable=True)
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_by_name = Column(String(128), nullable=True)
    approval_id = Column(String(64), nullable=True, index=True)
    candidate_id = Column(String(64), nullable=True, index=True)
    inbox_path = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "task": self.task,
            "mode": self.mode,
            "batch_name": self.batch_name,
            "source_type": self.source_type,
            "vehicle_scene": self.vehicle_scene,
            "collection_start": self.collection_start,
            "collection_end": self.collection_end,
            "data_path": self.data_path,
            "estimated_count": self.estimated_count,
            "remark": self.remark,
            "status": self.status,
            "owner_user_id": self.owner_user_id,
            "owner_name": self.owner_name,
            "submitted_by_user_id": self.submitted_by_user_id,
            "submitted_by_name": self.submitted_by_name,
            "submitted_by": self.submitted_by_name,
            "approval_id": self.approval_id,
            "candidate_id": self.candidate_id,
            "inbox_path": self.inbox_path,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class FeishuBitableLink(Base):
    """HSAP 批次与飞书多维表格行的对应关系。"""

    __tablename__ = "feishu_bitable_links"

    id = Column(Integer, primary_key=True)
    batch_key = Column(String(256), unique=True, nullable=False, index=True)
    record_id = Column(String(64), unique=True, nullable=True, index=True)
    delivery_id = Column(String(128), nullable=True, index=True)
    project = Column(String(32), nullable=False)
    task = Column(String(64), nullable=True)
    mode = Column(String(64), nullable=True)
    batch = Column(String(128), nullable=False)
    campaign_id = Column(String(64), nullable=True)
    inbox_path = Column(String(1024), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)


class FleetVehicle(Base):
    __tablename__ = "fleet_vehicles"

    id = Column(Integer, primary_key=True)
    plate_no = Column(String(32), nullable=False, index=True)
    tbox_device_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False, default="")
    team = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="active")
    last_lat = Column(Float, nullable=True)
    last_lng = Column(Float, nullable=True)
    last_speed_kmh = Column(Float, nullable=True)
    last_ts = Column(DateTime(timezone=True), nullable=True)
    online = Column(Boolean, nullable=False, default=False)
    meta_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def meta(self) -> dict:
        return json.loads(self.meta_json or "{}")

    def set_meta(self, data: dict) -> None:
        self.meta_json = json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plate_no": self.plate_no,
            "tbox_device_id": self.tbox_device_id,
            "name": self.name or self.plate_no,
            "team": self.team,
            "status": self.status,
            "last_lat": self.last_lat,
            "last_lng": self.last_lng,
            "last_speed_kmh": self.last_speed_kmh,
            "last_ts": self.last_ts.isoformat() if self.last_ts else None,
            "online": self.online,
            "meta": self.meta(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class FleetCollectionRun(Base):
    __tablename__ = "fleet_collection_runs"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("fleet_vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    run_no = Column(String(64), nullable=False, index=True)
    engineer = Column(String(128), nullable=True)
    project = Column(String(32), nullable=True)
    batch = Column(String(128), nullable=True)
    started_at = Column(DateTime(timezone=True), default=_utcnow)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    mileage_km = Column(Float, nullable=False, default=0.0)
    source = Column(String(32), nullable=False, default="tbox")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "run_no": self.run_no,
            "engineer": self.engineer,
            "project": self.project,
            "batch": self.batch,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status,
            "mileage_km": round(self.mileage_km or 0.0, 3),
            "source": self.source,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class FleetTrackPoint(Base):
    __tablename__ = "fleet_track_points"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("fleet_collection_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    ts = Column(DateTime(timezone=True), nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed_kmh = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    alt_m = Column(Float, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "ts": self.ts.isoformat() if self.ts else None,
            "lat": self.lat,
            "lng": self.lng,
            "speed_kmh": self.speed_kmh,
            "heading": self.heading,
            "alt_m": self.alt_m,
        }


class FleetRunMilestone(Base):
    __tablename__ = "fleet_run_milestones"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("fleet_collection_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False, default="")
    type = Column(String(32), nullable=False, default="waypoint")
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    mileage_km = Column(Float, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "name": self.name,
            "type": self.type,
            "lat": self.lat,
            "lng": self.lng,
            "mileage_km": self.mileage_km,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "payload": json.loads(self.payload_json or "{}"),
        }


class LabelingCampaignAccess(Base):
    """Campaign 级访问授权（内部/第三方），非派单。"""

    __tablename__ = "labeling_campaign_access"

    id = Column(Integer, primary_key=True)
    campaign_id = Column(String(64), nullable=False, index=True)
    principal_type = Column(String(32), nullable=False, default="role")
    principal_id = Column(String(128), nullable=False, index=True)
    access_role = Column(String(32), nullable=False, default="vendor")
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "principal_type": self.principal_type,
            "principal_id": self.principal_id,
            "access_role": self.access_role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LabelingExportJob(Base):
    """标注活动关联的 export / ml-predict 任务记录。"""

    __tablename__ = "labeling_export_jobs"

    id = Column(String(64), primary_key=True)
    campaign_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    job_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "action": self.action,
            "job_id": self.job_id,
            "status": self.status,
            "result": json.loads(self.result_json or "null") if self.result_json else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class LabelingCampaign(Base):
    """标注活动：与 pending 批次 (project, task, mode, batch, location) 一一对应。"""

    __tablename__ = "labeling_campaigns"

    id = Column(String(64), primary_key=True)
    project = Column(String(32), nullable=False, index=True)
    task = Column(String(64), nullable=False, index=True)
    mode = Column(String(64), nullable=True, index=True)
    batch = Column(String(128), nullable=False, index=True)
    pack = Column(String(64), nullable=True)
    location = Column(String(32), nullable=False, default="inbox")
    status = Column(String(32), nullable=False, default="not_opened", index=True)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    assigned_to_name = Column(String(128), nullable=True)
    config_xml = Column(Text, nullable=True)
    cvat_task_id = Column(Integer, nullable=True, index=True)
    cvat_job_url = Column(String(512), nullable=True)
    annotation_types = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project": self.project,
            "task": self.task,
            "mode": self.mode,
            "batch": self.batch,
            "pack": self.pack,
            "location": self.location,
            "status": self.status,
            "assigned_to_user_id": self.assigned_to_user_id,
            "assigned_to_name": self.assigned_to_name,
            "config_xml": self.config_xml,
            "cvat_task_id": self.cvat_task_id,
            "cvat_job_url": self.cvat_job_url,
            "annotation_types": self.annotation_types,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LabelingTaskAssignment(Base):
    """Campaign 内单张图（task_id）分包给标注员。"""

    __tablename__ = "labeling_task_assignments"
    __table_args__ = (UniqueConstraint("campaign_id", "task_id", name="uq_labeling_campaign_task"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(64), ForeignKey("labeling_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(String(32), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "assigned_by_user_id": self.assigned_by_user_id,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "completed_by_user_id": self.completed_by_user_id,
        }


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(128), nullable=True)
    category = Column(String(32), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=True)
    target_id = Column(String(128), nullable=True)
    summary = Column(String(512), nullable=True)
    detail_json = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "category": self.category,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "summary": self.summary,
            "detail": json.loads(self.detail_json) if self.detail_json else None,
            "ip_address": self.ip_address,
        }



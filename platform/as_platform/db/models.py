"""ORM 模型。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

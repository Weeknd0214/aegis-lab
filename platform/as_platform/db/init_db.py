"""数据库初始化、角色权限种子、jsonl 迁移。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from as_platform.config import (
    APPROVAL_QUEUE,
    FEISHU_ADMIN_DEPARTMENT_IDS,
    FEISHU_ADMIN_OPEN_IDS,
    IS_POSTGRES,
    IS_SQLITE,
    JOB_LOG,
    MANIFESTS,
)
from as_platform.db.engine import Base, engine, session_scope
from as_platform.db.models import Approval, Job, Permission, Role, User

# 角色 → 权限
ROLE_DEFS: dict[str, tuple[str, list[str]]] = {
    "admin": ("管理员", ["*"]),
    "reviewer": ("审核员", [
        "read:catalog", "read:pending", "read:jobs", "read:audit",
        "write:approval_review",
    ]),
    "engineer": ("算法工程师", [
        "read:catalog", "read:pending", "read:jobs", "read:audit",
        "write:approval_submit",
    ]),
    "labeler": ("标注协调", [
        "read:catalog", "read:pending", "write:approval_submit:register",
    ]),
    "viewer": ("只读访客", ["read:catalog", "read:pending"]),
}

PERMISSION_NAMES: dict[str, str] = {
    "*": "全部权限",
    "read:catalog": "查看数据目录",
    "read:pending": "查看送标/批次",
    "read:jobs": "查看 Job 队列",
    "read:audit": "查看审核记录",
    "write:approval_submit": "提交审核（训练/build 等）",
    "write:approval_submit:register": "提交批次登记审核",
    "write:approval_review": "批准/驳回审核",
    "admin:users": "用户与角色管理",
}


def init_database() -> None:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with session_scope() as db:
        _ensure_user_columns(db)
        _seed_roles_permissions(db)
        _import_jsonl_if_empty(db)
        _sync_postgres_sequences(db)


def _seed_roles_permissions(db: Session) -> None:
    perm_map: dict[str, Permission] = {}
    for code, name in PERMISSION_NAMES.items():
        p = db.query(Permission).filter_by(code=code).first()
        if not p:
            p = Permission(code=code, name=name)
            db.add(p)
            db.flush()
        perm_map[code] = p

    for role_code, (role_name, perm_codes) in ROLE_DEFS.items():
        role = db.query(Role).filter_by(code=role_code).first()
        if not role:
            role = Role(code=role_code, name=role_name)
            db.add(role)
            db.flush()
        role.permissions = [perm_map[c] for c in perm_codes if c in perm_map]


def _import_jsonl_if_empty(db: Session) -> None:
    if db.query(Approval).count() == 0 and APPROVAL_QUEUE.is_file():
        for line in APPROVAL_QUEUE.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if db.get(Approval, rec.get("id")):
                continue
            a = Approval(
                id=rec["id"],
                status=rec.get("status", "pending"),
                action=rec["action"],
                action_label=rec.get("action_label"),
                note=rec.get("note"),
                submitted_by_name=rec.get("submitted_by"),
                reviewed_by_name=rec.get("reviewed_by"),
                review_comment=rec.get("review_comment"),
                job_id=rec.get("job_id"),
            )
            a.set_params(rec.get("params") or {})
            if rec.get("result"):
                a.set_result(rec["result"])
            db.add(a)

    if db.query(Job).count() == 0 and JOB_LOG.is_file():
        for line in JOB_LOG.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if db.get(Job, rec.get("id")):
                continue
            j = Job(
                id=rec["id"],
                status=rec.get("status", "queued"),
                action=rec["action"],
                approval_id=rec.get("approval_id"),
            )
            j.set_params(rec.get("params") or {})
            if rec.get("result"):
                j.set_result(rec["result"])
            db.add(j)


def assign_default_role(db: Session, user: User) -> None:
    """新用户默认角色；支持 open_id / 部门白名单自动 admin。"""
    user_dept_ids = set(user.feishu_department_ids())
    if user.feishu_open_id and user.feishu_open_id in FEISHU_ADMIN_OPEN_IDS:
        role_code = "admin"
    elif user_dept_ids and user_dept_ids.intersection(FEISHU_ADMIN_DEPARTMENT_IDS):
        role_code = "admin"
    elif not user.roles:
        role_code = "engineer"
    else:
        return
    role = db.query(Role).filter_by(code=role_code).first()
    if role and role not in user.roles:
        user.roles.append(role)


def user_has_permission(user: User, permission: str) -> bool:
    if not user or not user.is_active:
        return False
    for role in user.roles:
        for p in role.permissions:
            if p.code == "*" or p.code == permission:
                return True
            # register_batch 专用权限
            if permission == "write:approval_submit:register" and p.code == "write:approval_submit":
                return True
    return False


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "feishu": {
            "open_id": user.feishu_open_id,
            "union_id": user.feishu_union_id,
            "user_id": user.feishu_user_id,
            "tenant_key": user.feishu_tenant_key,
            "department_ids": user.feishu_department_ids(),
        },
        "roles": [{"code": r.code, "name": r.name} for r in user.roles],
        "permissions": _collect_permissions(user),
    }


def _collect_permissions(user: User) -> list[str]:
    codes: set[str] = set()
    for role in user.roles:
        for p in role.permissions:
            codes.add(p.code)
    return sorted(codes)


def _sync_postgres_sequences(db: Session) -> None:
    """修复 PostgreSQL 自增序列与现有数据不一致问题。"""
    if not IS_POSTGRES:
        return
    # 当历史迁移手动插入了 id，sequence 可能还停留在 1，导致 duplicate key。
    db.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence('users', 'id'),
                COALESCE((SELECT MAX(id) FROM users), 1),
                true
            )
            """
        )
    )
    db.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence('roles', 'id'),
                COALESCE((SELECT MAX(id) FROM roles), 1),
                true
            )
            """
        )
    )
    db.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence('permissions', 'id'),
                COALESCE((SELECT MAX(id) FROM permissions), 1),
                true
            )
            """
        )
    )


def _ensure_user_columns(db: Session) -> None:
    user_columns = {
        "feishu_user_id": "VARCHAR(64)",
        "feishu_tenant_key": "VARCHAR(128)",
        "feishu_department_ids_json": "TEXT",
    }
    if IS_POSTGRES:
        for column, column_type in user_columns.items():
            db.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {column_type}"))
        db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_feishu_user_id ON users (feishu_user_id)"))
        return

    if IS_SQLITE:
        rows = db.execute(text("PRAGMA table_info(users)")).fetchall()
        existing = {str(row[1]) for row in rows}
        for column, column_type in user_columns.items():
            if column not in existing:
                db.execute(text(f"ALTER TABLE users ADD COLUMN {column} {column_type}"))

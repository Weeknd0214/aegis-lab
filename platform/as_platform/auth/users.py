"""用户服务。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session, joinedload

from as_platform.db.init_db import assign_default_role
from as_platform.db.models import Role, User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.permissions))
        .filter(User.id == user_id)
        .first()
    )


def upsert_feishu_user(db: Session, info: dict[str, Any]) -> User:
    open_id = info.get("open_id")
    user = db.query(User).filter(User.feishu_open_id == open_id).first()
    if not user:
        user = User(feishu_open_id=open_id)
        db.add(user)
    user.feishu_union_id = info.get("union_id") or user.feishu_union_id
    user.feishu_user_id = info.get("user_id") or user.feishu_user_id
    user.feishu_tenant_key = info.get("tenant_key") or user.feishu_tenant_key
    department_ids = info.get("department_ids")
    if isinstance(department_ids, list):
        user.feishu_department_ids_json = json.dumps(department_ids, ensure_ascii=False)
    user.name = info.get("name") or user.name
    user.email = info.get("email") or user.email
    user.avatar_url = info.get("avatar_url") or user.avatar_url
    user.is_active = True
    db.flush()
    assign_default_role(db, user)
    db.refresh(user)
    return get_user_by_id(db, user.id)  # type: ignore


def get_or_create_dev_user(db: Session, name: str = "开发用户") -> User:
    user = db.query(User).filter(User.name == name, User.feishu_open_id.is_(None)).first()
    if not user:
        user = User(name=name, email="dev@local")
        db.add(user)
        db.flush()
    admin = db.query(Role).filter_by(code="admin").first()
    if admin:
        user.roles = [admin]
    db.flush()
    return get_user_by_id(db, user.id)  # type: ignore


def list_users(db: Session) -> list[User]:
    return db.query(User).options(joinedload(User.roles)).order_by(User.id).all()


def list_users_paginated(
    db: Session,
    search: str = "",
    role_code: str = "",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[User], int]:
    q = db.query(User).options(joinedload(User.roles))
    if search:
        like = f"%{search}%"
        q = q.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    if role_code:
        q = q.join(User.roles).filter(Role.code == role_code)
    total = q.count()
    users = q.order_by(User.id).offset(offset).limit(limit).all()
    return users, total


def set_user_roles(db: Session, user_id: int, role_codes: list[str]) -> User | None:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    roles = db.query(Role).filter(Role.code.in_(role_codes)).all()
    user.roles = roles
    db.flush()
    return user

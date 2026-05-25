"""FastAPI 认证依赖。"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from as_platform.auth.jwt import decode_access_token
from as_platform.config import DEV_AUTH_ENABLED
from as_platform.db.engine import get_db
from as_platform.db.init_db import user_has_permission
from as_platform.db.models import Role, User

_bearer = HTTPBearer(auto_error=False)


def _load_user(db: Session, user_id: int) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.permissions))
        .filter(User.id == user_id, User.is_active.is_(True))
        .first()
    )


def get_current_user_optional(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    if not creds:
        return None
    payload = decode_access_token(creds.credentials)
    if not payload or "sub" not in payload:
        return None
    return _load_user(db, int(payload["sub"]))


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未登录，请先飞书登录")
    return user


def require_permission(permission: str):
    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not user_has_permission(user, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"缺少权限: {permission}")
        return user

    return _dep


def require_any_permission(*permissions: str):
    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if any(user_has_permission(user, p) for p in permissions):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="权限不足")

    return _dep


def can_submit_action(user: User, action: str) -> bool:
    if user_has_permission(user, "write:approval_submit"):
        return True
    if action == "register_batch" and user_has_permission(user, "write:approval_submit:register"):
        return True
    return False

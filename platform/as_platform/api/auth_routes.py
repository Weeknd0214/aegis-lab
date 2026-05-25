"""认证与用户管理 API。"""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from as_platform.auth.deps import get_current_user, require_permission
from as_platform.auth.feishu import build_authorize_url, exchange_code, is_feishu_configured, verify_state
from as_platform.auth.jwt import create_access_token
from as_platform.auth.users import get_or_create_dev_user, list_users, set_user_roles, upsert_feishu_user
from as_platform.config import DEV_AUTH_ENABLED, FRONTEND_URL
from as_platform.db.engine import get_db
from as_platform.db.init_db import user_to_dict
from as_platform.db.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class DevLoginBody(BaseModel):
    name: str = "开发用户"


class SetRolesBody(BaseModel):
    role_codes: list[str] = Field(default_factory=list)


@router.get("/config")
def auth_config() -> dict[str, Any]:
    return {
        "feishu_enabled": is_feishu_configured(),
        "dev_auth_enabled": DEV_AUTH_ENABLED and not is_feishu_configured(),
    }


@router.get("/feishu/authorize")
def feishu_authorize():
    if not is_feishu_configured():
        raise HTTPException(503, "未配置飞书应用，请设置 FEISHU_APP_ID / FEISHU_APP_SECRET")
    url, _ = build_authorize_url()
    return RedirectResponse(url)


@router.get("/feishu/callback")
def feishu_callback(code: str, state: str, db: Annotated[Session, Depends(get_db)]):
    if not verify_state(state):
        raise HTTPException(400, "无效的 state，请重新登录")
    try:
        info = exchange_code(code)
    except Exception as e:
        raise HTTPException(502, f"飞书登录失败: {e}") from e
    user = upsert_feishu_user(db, info)
    db.commit()
    token = create_access_token(user.id)
    # 避免 BrowserRouter 直达路径 404，统一回根路径并附带 token
    qs = urlencode({"token": token})
    return RedirectResponse(f"{FRONTEND_URL}/?{qs}")


@router.post("/dev/login")
def dev_login(body: DevLoginBody, db: Annotated[Session, Depends(get_db)]):
    if not DEV_AUTH_ENABLED or is_feishu_configured():
        raise HTTPException(403, "开发登录未启用")
    user = get_or_create_dev_user(db, body.name)
    db.commit()
    token = create_access_token(user.id)
    return {"access_token": token, "user": user_to_dict(user)}


@router.get("/me")
def auth_me(user: Annotated[User, Depends(get_current_user)]):
    return user_to_dict(user)


@router.get("/users")
def auth_list_users(
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
):
    return {"items": [user_to_dict(u) for u in list_users(db)]}


@router.put("/users/{user_id}/roles")
def auth_set_roles(
    user_id: int,
    body: SetRolesBody,
    _user: Annotated[User, Depends(require_permission("admin:users"))],
    db: Annotated[Session, Depends(get_db)],
):
    user = set_user_roles(db, user_id, body.role_codes)
    if not user:
        raise HTTPException(404, "用户不存在")
    db.commit()
    return user_to_dict(user)

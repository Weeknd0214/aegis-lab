"""飞书 OAuth 登录。"""
from __future__ import annotations

import json
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from as_platform.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_REDIRECT_URI, JWT_SECRET
from as_platform.db.models import User

FEISHU_AUTHORIZE_URL = "https://passport.feishu.cn/suite/passport/oauth/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_USER_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
FEISHU_TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_CONTACT_USER_URL = "https://open.feishu.cn/open-apis/contact/v3/users/{user_id}"
FEISHU_CONTACT_USERS_URL = "https://open.feishu.cn/open-apis/contact/v3/users"
FEISHU_DEPARTMENTS_URL = "https://open.feishu.cn/open-apis/contact/v3/departments"
FEISHU_DEPARTMENT_CHILDREN_URL = "https://open.feishu.cn/open-apis/contact/v3/departments/{department_id}/children"
FEISHU_USERS_BY_DEPT_URL = "https://open.feishu.cn/open-apis/contact/v3/users/find_by_department"

STATE_ALG = "HS256"
STATE_EXPIRE_MINUTES = 10


def is_feishu_configured() -> bool:
    return bool(FEISHU_APP_ID and FEISHU_APP_SECRET)


def build_authorize_url() -> tuple[str, str]:
    # 使用签名 state，避免服务重启/多进程导致内存 state 丢失
    now = datetime.now(timezone.utc)
    state = jwt.encode(
        {
            "nonce": secrets.token_urlsafe(12),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=STATE_EXPIRE_MINUTES)).timestamp()),
            "typ": "feishu_oauth_state",
        },
        JWT_SECRET,
        algorithm=STATE_ALG,
    )
    params = {
        "client_id": FEISHU_APP_ID,
        "redirect_uri": FEISHU_REDIRECT_URI,
        "response_type": "code",
        "state": state,
    }
    return f"{FEISHU_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}", state


def verify_state(state: str) -> bool:
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[STATE_ALG])
        return payload.get("typ") == "feishu_oauth_state"
    except JWTError:
        return False


def exchange_code(code: str) -> dict[str, Any]:
    """用授权码换 user_access_token 并拉取用户信息。"""
    with httpx.Client(timeout=30.0) as client:
        token_resp = client.post(
            FEISHU_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "app_id": FEISHU_APP_ID,
                "app_secret": FEISHU_APP_SECRET,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        if token_data.get("code") != 0:
            raise RuntimeError(token_data.get("msg") or "飞书 token 交换失败")

        access_token = token_data["data"]["access_token"]
        user_resp = client.get(
            FEISHU_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()
        if user_data.get("code") != 0:
            raise RuntimeError(user_data.get("msg") or "飞书用户信息获取失败")

        info = user_data["data"]
        department_ids: list[str] = []
        user_id = info.get("user_id")
        tenant_key = info.get("tenant_key")
        open_id = info.get("open_id") or info.get("openId")
        if open_id:
            try:
                tenant_access_token = _get_tenant_access_token(client)
                contact_user = _get_contact_user_profile(client, tenant_access_token, open_id)
                user_id = contact_user.get("user_id") or user_id
                tenant_key = contact_user.get("tenant_key") or tenant_key
                raw_department_ids = contact_user.get("department_ids")
                if isinstance(raw_department_ids, list):
                    department_ids = [str(x) for x in raw_department_ids if x]
            except Exception:
                # 联系人接口失败时不阻断登录
                department_ids = []

        return {
            "open_id": open_id,
            "union_id": info.get("union_id") or info.get("unionId"),
            "user_id": user_id,
            "tenant_key": tenant_key,
            "department_ids": department_ids,
            "name": info.get("name") or info.get("en_name") or "飞书用户",
            "email": info.get("email") or info.get("enterprise_email"),
            "avatar_url": info.get("avatar_url") or info.get("avatar_big"),
        }


def _get_tenant_access_token(client: httpx.Client) -> str:
    resp = client.post(
        FEISHU_TENANT_TOKEN_URL,
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg") or "飞书 tenant token 获取失败")
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError("飞书 tenant token 为空")
    return token


def _get_contact_user_profile(
    client: httpx.Client, tenant_access_token: str, open_id: str
) -> dict[str, Any]:
    resp = client.get(
        FEISHU_CONTACT_USER_URL.format(user_id=urllib.parse.quote(open_id, safe="")),
        params={"user_id_type": "open_id", "department_id_type": "open_department_id"},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg") or "飞书联系人信息获取失败")
    return data.get("data", {}).get("user", {})


def _parse_contact_user(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "open_id": item.get("open_id"),
        "union_id": item.get("union_id"),
        "user_id": item.get("user_id"),
        "name": item.get("name") or item.get("en_name") or item.get("nickname"),
        "email": item.get("email") or item.get("enterprise_email"),
        "mobile": item.get("mobile"),
        "avatar_url": item.get("avatar", {}).get("avatar_240")
        if isinstance(item.get("avatar"), dict)
        else None,
        "department_ids": item.get("department_ids", []),
    }


def _paginate_feishu_get(
    client: httpx.Client,
    token: str,
    url: str,
    params: dict[str, str | int],
) -> tuple[list[dict[str, Any]], str | None]:
    """分页 GET，返回 (items, error_message)。"""
    items: list[dict[str, Any]] = []
    page_token = ""
    error_msg: str | None = None
    while True:
        req = dict(params)
        if page_token:
            req["page_token"] = page_token
        resp = client.get(url, params=req, headers={"Authorization": f"Bearer {token}"})
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or data.get("code") not in (0, None):
            return items, data.get("msg") or f"HTTP {resp.status_code}"
        if data.get("code") == 0:
            items.extend(data.get("data", {}).get("items", []))
        page_token = data.get("data", {}).get("page_token", "")
        if not page_token:
            break
    return items, error_msg


def _fetch_department_map(client: httpx.Client, token: str) -> tuple[dict[str, str], str | None]:
    """递归拉取全部部门，返回 {open_department_id: name}。"""
    dept_map: dict[str, str] = {"0": "全员"}
    # 优先：从根部门递归子部门（需全员通讯录范围）
    children, err = _paginate_feishu_get(
        client,
        token,
        FEISHU_DEPARTMENT_CHILDREN_URL.format(department_id="0"),
        {
            "department_id_type": "open_department_id",
            "fetch_child": "true",
            "page_size": 50,
        },
    )
    if err and "no dept authority" in err:
        return {}, err
    for item in children:
        did = item.get("open_department_id", "")
        if did:
            dept_map[did] = item.get("name", "") or did
    if dept_map and len(dept_map) > 1:
        return dept_map, None

    # 回退：平铺部门列表
    flat, err2 = _paginate_feishu_get(
        client,
        token,
        FEISHU_DEPARTMENTS_URL,
        {"page_size": 50, "department_id_type": "open_department_id"},
    )
    for item in flat:
        did = item.get("open_department_id", "")
        if did:
            dept_map[did] = item.get("name", "") or did
    return dept_map, err2 or err


def _fetch_users_by_department(
    client: httpx.Client, token: str, department_id: str
) -> tuple[list[dict[str, Any]], str | None]:
    raw, err = _paginate_feishu_get(
        client,
        token,
        FEISHU_USERS_BY_DEPT_URL,
        {
            "department_id": department_id,
            "user_id_type": "open_id",
            "department_id_type": "open_department_id",
            "page_size": 50,
        },
    )
    return [_parse_contact_user(x) for x in raw if x.get("open_id")], err


def _fetch_users_list(
    client: httpx.Client,
    token: str,
    *,
    department_id: str | None = None,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    params: dict[str, str | int] = {
        "user_id_type": "open_id",
        "department_id_type": "open_department_id",
        "page_size": min(page_size, 50),
    }
    if department_id is not None:
        params["department_id"] = department_id
    raw, err = _paginate_feishu_get(client, token, FEISHU_CONTACT_USERS_URL, params)
    return [_parse_contact_user(x) for x in raw if x.get("open_id")], err


def fetch_feishu_users(page_size: int = 50) -> tuple[list[dict[str, Any]], dict[str, str], str | None]:
    """从飞书通讯录拉取组织用户（按部门递归 + 多策略回退）。

    返回 (users, dept_name_map, error_message)。
    若应用通讯录范围不是「全部员工」，可能只能同步到极少数成员。
    """
    if not is_feishu_configured():
        return [], {}, "飞书应用未配置"

    error_msg: str | None = None
    scope_warning: str | None = None
    users_by_id: dict[str, dict[str, Any]] = {}
    try:
        with httpx.Client(timeout=60) as client:
            token = _get_tenant_access_token(client)
            dept_map, dept_err = _fetch_department_map(client, token)

            # 策略 1：按部门拉取直属用户（可覆盖全员）
            if dept_map:
                dept_ids = [d for d in dept_map if d != "0"] or ["0"]
                if "0" not in dept_ids:
                    dept_ids = ["0", *dept_ids]
                for did in dept_ids:
                    batch, err = _fetch_users_by_department(client, token, did)
                    if err and not error_msg:
                        error_msg = err
                    for u in batch:
                        oid = u.get("open_id")
                        if oid:
                            users_by_id[oid] = u

            # 策略 2：根部门用户列表
            if not users_by_id:
                batch, err = _fetch_users_list(client, token, department_id="0", page_size=page_size)
                if err and not error_msg:
                    error_msg = err
                for u in batch:
                    oid = u.get("open_id")
                    if oid:
                        users_by_id[oid] = u

            # 策略 3：权限范围内独立成员（回退，通常很少）
            if not users_by_id:
                batch, err = _fetch_users_list(client, token, page_size=page_size)
                if err and not error_msg:
                    error_msg = err
                for u in batch:
                    oid = u.get("open_id")
                    if oid:
                        users_by_id[oid] = u

            if dept_err and "no dept authority" in (dept_err or ""):
                scope_warning = (
                    "应用通讯录范围未包含「全部员工」，无法按部门拉取全员。"
                    "请在开放平台 → 版本管理与发布 → 可用范围/通讯录权限 设为全部员工后重新发布。"
                )
            elif len(users_by_id) <= 5 and dept_err:
                scope_warning = (
                    f"仅同步到 {len(users_by_id)} 人，可能通讯录范围过窄。"
                    "请将应用通讯录权限范围调整为全部员工。"
                )

            users = list(users_by_id.values())
            if scope_warning:
                # 附带在 error 字段供前端展示（有用户时不算硬错误）
                if not users:
                    error_msg = error_msg or scope_warning
                elif not error_msg:
                    error_msg = scope_warning
            return users, dept_map, error_msg if not users else (scope_warning or None)
    except Exception as exc:
        return [], {}, str(exc)


def sync_feishu_users_to_db(db: Session) -> dict[str, int | str | None]:
    """同步飞书用户到数据库，返回 {created, updated, total, error}。"""
    users, dept_map, error_msg = fetch_feishu_users()
    created, updated = 0, 0
    for info in users:
        open_id = info.get("open_id")
        if not open_id:
            continue
        user = db.query(User).filter(User.feishu_open_id == open_id).first()
        if not user:
            user = User(feishu_open_id=open_id)
            db.add(user)
            created += 1
        else:
            updated += 1
        user.feishu_union_id = info.get("union_id") or user.feishu_union_id
        user.feishu_user_id = info.get("user_id") or user.feishu_user_id
        user.name = (
            info.get("name")
            or info.get("email")
            or user.name
            or f"飞书用户-{open_id[-6:]}"
        )
        user.email = info.get("email") or user.email or user.email
        user.avatar_url = info.get("avatar_url") or user.avatar_url
        dept_ids = info.get("department_ids")
        if isinstance(dept_ids, list) and dept_ids:
            dept_names = [dept_map.get(str(did), str(did)) for did in dept_ids]
            user.feishu_department_ids_json = json.dumps(dept_names, ensure_ascii=False)
        user.is_active = True
    db.flush()
    return {"created": created, "updated": updated, "total": len(users), "error": error_msg}

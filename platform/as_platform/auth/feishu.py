"""飞书 OAuth 登录。"""
from __future__ import annotations

import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt

from as_platform.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_REDIRECT_URI, JWT_SECRET

FEISHU_AUTHORIZE_URL = "https://passport.feishu.cn/suite/passport/oauth/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v1/access_token"
FEISHU_USER_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
FEISHU_TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_CONTACT_USER_URL = "https://open.feishu.cn/open-apis/contact/v3/users/{user_id}"

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

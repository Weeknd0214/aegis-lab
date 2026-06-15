"""飞书群消息通知（出站，内网可用）。"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from as_platform.auth.feishu import _get_tenant_access_token
from as_platform.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_LABELING_CHAT_ID

logger = logging.getLogger(__name__)

IM_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

IM_MESSAGE_SCOPE_URL = (
    f"https://open.feishu.cn/app/{FEISHU_APP_ID}/auth"
    "?q=im:message:send_as_bot,im:message:send,im:message"
    "&op_from=openapi&token_type=tenant"
    if FEISHU_APP_ID
    else ""
)

FEISHU_BOT_SETUP_URL = f"https://open.feishu.cn/app/{FEISHU_APP_ID}/bot" if FEISHU_APP_ID else ""
FEISHU_PUBLISH_URL = f"https://open.feishu.cn/app/{FEISHU_APP_ID}/appPublish" if FEISHU_APP_ID else ""


def _feishu_send_error_hint(message: str) -> dict[str, str]:
    """将飞书 API 英文报错映射为可操作的中文提示。"""
    msg = message or ""
    if "Bot ability is not activated" in msg:
        return {
            "reason": "bot_not_activated",
            "help_text": "应用未启用「机器人」能力：开放平台 → 应用能力 → 添加机器人 → 创建版本并发布",
            "help_url": FEISHU_BOT_SETUP_URL or IM_MESSAGE_SCOPE_URL,
        }
    if "NO availability" in msg or "230013" in msg:
        return {
            "reason": "user_out_of_scope",
            "help_text": "你在机器人可用范围外：版本管理与发布 → 编辑可用范围 → 加入全员或你的部门 → 重新发布",
            "help_url": FEISHU_PUBLISH_URL or IM_MESSAGE_SCOPE_URL,
        }
    if "im:message" in msg or "Access denied" in msg:
        return {
            "reason": "missing_im_scope",
            "help_text": "应用未开通「发送消息」权限，请在权限管理中申请 im:message:send_as_bot",
            "help_url": IM_MESSAGE_SCOPE_URL,
        }
    return {
        "reason": "send_failed",
        "help_text": msg[:120],
        "help_url": IM_MESSAGE_SCOPE_URL,
    }


def _parse_feishu_send_response(resp: httpx.Response) -> dict[str, Any]:
    data = resp.json() if resp.content else {}
    if resp.status_code < 400 and data.get("code") in (0, None):
        return {"ok": True}
    msg = data.get("msg") or f"HTTP {resp.status_code}"
    hint = _feishu_send_error_hint(msg)
    return {"ok": False, "message": msg, **hint}


def is_notify_configured() -> bool:
    return bool(FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_LABELING_CHAT_ID)


def send_chat_text(text: str) -> dict[str, Any]:
    if not is_notify_configured():
        return {"ok": False, "message": "未配置 FEISHU_LABELING_CHAT_ID"}
    with httpx.Client(timeout=30.0) as client:
        token = _get_tenant_access_token(client)
        resp = client.post(
            IM_MSG_URL,
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": FEISHU_LABELING_CHAT_ID,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        resp.raise_for_status()
        return _parse_feishu_send_response(resp)


def send_chat_async(text: str) -> None:
    """异步发送飞书群消息，不阻塞主流程。"""
    import threading
    threading.Thread(target=_send_chat_safe, args=(text,), daemon=True, name="feishu-notify").start()


def send_user_text(open_id: str, text: str) -> dict[str, Any]:
    """向指定飞书用户发送私聊消息（需应用具备 im:message 权限）。"""
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return {"ok": False, "message": "飞书未配置"}
    if not open_id:
        return {"ok": False, "message": "open_id 为空"}
    try:
        with httpx.Client(timeout=30.0) as client:
            token = _get_tenant_access_token(client)
            resp = client.post(
                IM_MSG_URL,
                params={"receive_id_type": "open_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": open_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400 or data.get("code") not in (0, None):
                result = _parse_feishu_send_response(resp)
                logger.warning(
                    "飞书私聊发送失败 open_id=%s reason=%s: %s",
                    open_id[:12],
                    result.get("reason"),
                    result.get("message"),
                )
                return result
            return {"ok": True}
    except Exception as exc:
        logger.warning("飞书私聊发送异常 open_id=%s: %s", open_id[:12], exc)
        hint = _feishu_send_error_hint(str(exc))
        return {"ok": False, "message": str(exc), **hint}


def send_user_async(open_id: str, text: str) -> None:
    """异步向飞书用户发私聊，不阻塞主流程。"""
    import threading
    threading.Thread(
        target=_send_user_safe,
        args=(open_id, text),
        daemon=True,
        name="feishu-user-notify",
    ).start()


def _send_chat_safe(text: str) -> None:
    try:
        send_chat_text(text)
    except Exception:
        pass


def _send_user_safe(open_id: str, text: str) -> None:
    try:
        send_user_text(open_id, text)
    except Exception:
        pass


def notify_labeling_assignment(
    *,
    open_id: str,
    assignee_name: str,
    task: str,
    batch: str,
    count: int,
    campaign_id: str,
) -> dict[str, Any]:
    """分配标注任务后向被指派人发送飞书私聊通知，返回发送结果。"""
    from as_platform.config import FRONTEND_URL

    link = f"{FRONTEND_URL.rstrip('/')}/labeling/my-tasks?campaign={campaign_id}"
    text = (
        f"[HSAP] 您有新的标注任务\n"
        f"被指派人: {assignee_name}\n"
        f"任务: {task} / 批次: {batch}\n"
        f"分配数量: {count} 张\n"
        f"请打开我的标注: {link}"
    )
    result = send_user_text(open_id, text)
    if not result.get("ok") and is_notify_configured():
        # 私聊失败时尝试发到标注协作群
        fallback = send_chat_text(
            f"[HSAP] 任务分配通知\n"
            f"@{assignee_name} 您有 {count} 张新标注任务\n"
            f"任务: {task} / 批次: {batch}\n"
            f"打开我的标注: {link}"
        )
        if fallback.get("ok"):
            return {"ok": True, "channel": "chat", "name": assignee_name}
    return {**result, "channel": "dm", "name": assignee_name}


def notify_labeling_assignment_async(
    *,
    open_id: str,
    assignee_name: str,
    task: str,
    batch: str,
    count: int,
    campaign_id: str,
) -> None:
    import threading
    threading.Thread(
        target=notify_labeling_assignment,
        kwargs={
            "open_id": open_id,
            "assignee_name": assignee_name,
            "task": task,
            "batch": batch,
            "count": count,
            "campaign_id": campaign_id,
        },
        daemon=True,
        name="feishu-assign-notify",
    ).start()


def notify_batch_progress(
    *,
    delivery_id: str,
    task: str,
    batch_name: str,
    progress: str,
    link: str,
) -> dict[str, Any]:
    text = (
        f"[HSAP] 标注进度 {delivery_id or batch_name}\n"
        f"任务: {task} / 批次: {batch_name}\n"
        f"进度: {progress}\n"
        f"链接: {link}"
    )
    return send_chat_text(text)

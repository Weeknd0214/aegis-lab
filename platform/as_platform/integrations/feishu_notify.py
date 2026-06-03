"""飞书群消息通知（出站，内网可用）。"""
from __future__ import annotations

import json
from typing import Any

import httpx

from as_platform.auth.feishu import _get_tenant_access_token
from as_platform.config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_LABELING_CHAT_ID

IM_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


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
        data = resp.json()
        if data.get("code") != 0:
            return {"ok": False, "message": data.get("msg") or "send failed"}
        return {"ok": True}


def send_chat_async(text: str) -> None:
    """异步发送飞书消息，不阻塞主流程。"""
    import threading
    threading.Thread(target=_send_safe, args=(text,), daemon=True, name="feishu-notify").start()


def _send_safe(text: str) -> None:
    try:
        send_chat_text(text)
    except Exception:
        pass  # 通知失败不影响业务流程


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

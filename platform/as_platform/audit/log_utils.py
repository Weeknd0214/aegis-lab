"""操作审计日志工具。异步写入，不阻塞主流程。"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from as_platform.db.models import OperationLog


def log_op(
    *,
    user_id: int | None = None,
    user_name: str | None = None,
    category: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    summary: str = "",
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """异步记录操作日志。"""
    threading.Thread(
        target=_write_log,
        args=(user_id, user_name, category, action, target_type, target_id, summary, detail, ip_address),
        daemon=True,
        name=f"audit-log-{action}",
    ).start()


def _write_log(
    user_id: int | None,
    user_name: str | None,
    category: str,
    action: str,
    target_type: str | None,
    target_id: str | None,
    summary: str,
    detail: dict[str, Any] | None,
    ip_address: str | None,
) -> None:
    try:
        from as_platform.db.engine import session_scope

        with session_scope() as db:
            log = OperationLog(
                timestamp=datetime.now(timezone.utc),
                user_id=user_id,
                user_name=user_name,
                category=category,
                action=action,
                target_type=target_type,
                target_id=str(target_id)[:128] if target_id else None,
                summary=summary[:512] if summary else None,
                detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
                ip_address=ip_address,
            )
            db.add(log)
            db.commit()
    except Exception:
        pass  # 日志写入失败不影响业务

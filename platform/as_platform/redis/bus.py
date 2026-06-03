"""Redis 连接与 Job 事件总线。"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from as_platform.config import JOB_QUEUE_KEY, REDIS_URL

try:
    import redis
except ImportError:
    redis = None  # type: ignore


@lru_cache(maxsize=1)
def get_redis():
    if not REDIS_URL or redis is None:
        return None
    return redis.from_url(REDIS_URL, decode_responses=True)


def ping_redis() -> bool:
    try:
        r = get_redis()
        return bool(r and r.ping())
    except Exception:
        return False


def publish(event: str, payload: dict[str, Any]) -> None:
    try:
        r = get_redis()
        if not r:
            return
        r.publish("as:events", json.dumps({"event": event, **payload}, ensure_ascii=False))
    except Exception:
        return


def push_job(job_id: str) -> None:
    r = get_redis()
    if not r:
        raise RuntimeError("Redis 未配置，无法使用 worker 模式")
    r.lpush(JOB_QUEUE_KEY, job_id)
    publish("job.queued", {"job_id": job_id})


def pop_job(timeout: int = 5) -> str | None:
    r = get_redis()
    if not r:
        return None
    item = r.brpop(JOB_QUEUE_KEY, timeout=timeout)
    return item[1] if item else None

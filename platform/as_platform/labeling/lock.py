"""标注任务 Redis 互斥锁（campaign + task 粒度）。"""
from __future__ import annotations

import json
import time
from typing import Any

from as_platform.redis.bus import get_redis

LOCK_TTL_SEC = 300
_LOCK_PREFIX = "labeling:lock:"
# API 进程内回退（无 Redis 时）
_memory: dict[str, dict[str, Any]] = {}


def _key(campaign_id: str, task_id: str) -> str:
    return f"{_LOCK_PREFIX}{campaign_id}:{task_id}"


def _parse_holder(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"name": raw}


def acquire_lock(campaign_id: str, task_id: str, *, user_id: int, user_name: str) -> dict[str, Any]:
    payload = json.dumps({"user_id": user_id, "name": user_name}, ensure_ascii=False)
    r = get_redis()
    if not r:
        now = time.time()
        mem = _memory.get(_key(campaign_id, task_id))
        if mem and mem.get("user_id") != user_id and now < mem.get("expires_at", 0):
            return {"ok": False, "holder": mem.get("name"), "user_id": mem.get("user_id")}
        _memory[_key(campaign_id, task_id)] = {
            "user_id": user_id,
            "name": user_name,
            "expires_at": now + LOCK_TTL_SEC,
        }
        return {"ok": True, "holder": user_name, "ttl_sec": LOCK_TTL_SEC, "backend": "memory"}

    key = _key(campaign_id, task_id)
    if r.set(key, payload, nx=True, ex=LOCK_TTL_SEC):
        return {"ok": True, "holder": user_name, "ttl_sec": LOCK_TTL_SEC, "backend": "redis"}
    existing = _parse_holder(r.get(key))
    if existing and existing.get("user_id") == user_id:
        r.expire(key, LOCK_TTL_SEC)
        return {"ok": True, "holder": user_name, "ttl_sec": LOCK_TTL_SEC, "renewed": True, "backend": "redis"}
    return {
        "ok": False,
        "holder": (existing or {}).get("name"),
        "user_id": (existing or {}).get("user_id"),
        "backend": "redis",
    }


def release_lock(campaign_id: str, task_id: str, *, user_id: int) -> dict[str, Any]:
    r = get_redis()
    if not r:
        key = _key(campaign_id, task_id)
        mem = _memory.get(key)
        if mem and mem.get("user_id") == user_id:
            _memory.pop(key, None)
            return {"ok": True, "released": True, "backend": "memory"}
        return {"ok": True, "released": False, "backend": "memory"}

    key = _key(campaign_id, task_id)
    existing = _parse_holder(r.get(key))
    if not existing:
        return {"ok": True, "released": False, "backend": "redis"}
    if existing.get("user_id") != user_id:
        return {"ok": False, "holder": existing.get("name"), "backend": "redis"}
    r.delete(key)
    return {"ok": True, "released": True, "backend": "redis"}


def renew_lock(campaign_id: str, task_id: str, *, user_id: int) -> dict[str, Any]:
    r = get_redis()
    if not r:
        key = _key(campaign_id, task_id)
        mem = _memory.get(key)
        if mem and mem.get("user_id") == user_id:
            mem["expires_at"] = time.time() + LOCK_TTL_SEC
            return {"ok": True, "ttl_sec": LOCK_TTL_SEC, "backend": "memory"}
        return {"ok": False, "backend": "memory"}

    key = _key(campaign_id, task_id)
    existing = _parse_holder(r.get(key))
    if not existing or existing.get("user_id") != user_id:
        return {"ok": False, "holder": (existing or {}).get("name"), "backend": "redis"}
    r.expire(key, LOCK_TTL_SEC)
    return {"ok": True, "ttl_sec": LOCK_TTL_SEC, "backend": "redis"}

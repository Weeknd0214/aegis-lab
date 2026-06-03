"""标注进度统计与按人分包。"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from as_platform.db.engine import session_scope
from as_platform.db.models import LabelingCampaign, LabelingTaskAssignment, User
from as_platform.labeling.annotate import (
    _annotations_dir,
    _iter_batch_images,
    _task_id_for_image,
    resolve_campaign_batch_dir,
)

COORDINATOR_ROLES = frozenset({"labeler", "admin", "engineer", "reviewer"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def user_role_codes(user: User) -> set[str]:
    return {r.code for r in (user.roles or [])}


def user_is_coordinator(user: User) -> bool:
    codes = user_role_codes(user)
    if codes & COORDINATOR_ROLES:
        return True
    perms: set[str] = set()
    for r in user.roles or []:
        for p in r.permissions or []:
            if p.code:
                perms.add(p.code)
    return "*" in perms or "write:labeling_assign" in perms


def list_campaign_task_ids(campaign_id: str) -> list[str]:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
    images = _iter_batch_images(batch_dir)
    return [_task_id_for_image(img, batch_dir) for img in images]


def _annotation_has_result(path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    result = data.get("result")
    if result is None:
        return False
    if isinstance(result, list):
        return len(result) > 0
    if isinstance(result, dict):
        return len(result) > 0
    return bool(result)


def count_completed_tasks(batch_dir) -> set[str]:
    ann_dir = _annotations_dir(batch_dir)
    done: set[str] = set()
    if not ann_dir.is_dir():
        return done
    for p in ann_dir.glob("*.json"):
        if _annotation_has_result(p):
            done.add(p.stem)
    return done


def _user_name_map(db, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.query(User).filter(User.id.in_(user_ids)).all()
    return {u.id: u.name or f"user-{u.id}" for u in rows}


def campaign_progress(campaign_id: str) -> dict[str, Any]:
    with session_scope() as db:
        camp = db.get(LabelingCampaign, campaign_id)
        if not camp:
            raise FileNotFoundError("campaign not found")
        batch_dir = resolve_campaign_batch_dir(camp)
        all_ids = [_task_id_for_image(img, batch_dir) for img in _iter_batch_images(batch_dir)]
        completed_ids = count_completed_tasks(batch_dir)
        rows = (
            db.query(LabelingTaskAssignment)
            .filter(LabelingTaskAssignment.campaign_id == campaign_id)
            .all()
        )
        user_ids = {r.user_id for r in rows} | {r.completed_by_user_id for r in rows if r.completed_by_user_id}
        names = _user_name_map(db, user_ids)

    total = len(all_ids)
    completed = len(completed_ids)
    assigned = len(rows)
    by_user_agg: dict[int, dict[str, int]] = defaultdict(lambda: {"assigned": 0, "completed": 0})
    for r in rows:
        by_user_agg[r.user_id]["assigned"] += 1
        if r.completed_at or r.task_id in completed_ids:
            by_user_agg[r.user_id]["completed"] += 1

    by_user = []
    for uid, stats in sorted(by_user_agg.items(), key=lambda x: names.get(x[0], "")):
        a = stats["assigned"]
        c = stats["completed"]
        by_user.append(
            {
                "user_id": uid,
                "name": names.get(uid, f"user-{uid}"),
                "assigned": a,
                "completed": c,
                "percent": round(100.0 * c / a, 1) if a else 0.0,
            }
        )

    return {
        "campaign_id": campaign_id,
        "total_tasks": total,
        "completed_tasks": completed,
        "assigned_tasks": assigned,
        "unassigned_tasks": max(0, total - assigned),
        "percent": round(100.0 * completed / total, 1) if total else 0.0,
        "by_user": by_user,
    }


def campaign_progress_summary(campaign_id: str) -> dict[str, int]:
    try:
        p = campaign_progress(campaign_id)
        return {
            "total_tasks": p["total_tasks"],
            "completed_tasks": p["completed_tasks"],
            "assigned_tasks": p["assigned_tasks"],
        }
    except FileNotFoundError:
        return {"total_tasks": 0, "completed_tasks": 0, "assigned_tasks": 0}


def get_assigned_task_ids(campaign_id: str, user_id: int | None = None) -> set[str]:
    with session_scope() as db:
        q = db.query(LabelingTaskAssignment.task_id).filter(
            LabelingTaskAssignment.campaign_id == campaign_id
        )
        if user_id is not None:
            q = q.filter(LabelingTaskAssignment.user_id == user_id)
        return {row[0] for row in q.all()}


def _assign_result(campaign_id: str, created: int) -> dict[str, Any]:
    prog = campaign_progress(campaign_id)
    return {"assigned": created, "by_user": prog["by_user"], "progress": prog}


def assign_tasks_even(
    campaign_id: str,
    user_ids: list[int],
    *,
    assigned_by_user_id: int,
) -> dict[str, Any]:
    if not user_ids:
        raise ValueError("user_ids 不能为空")
    now = _utcnow()
    all_ids = list_campaign_task_ids(campaign_id)
    with session_scope() as db:
        existing = {
            r.task_id
            for r in db.query(LabelingTaskAssignment)
            .filter(LabelingTaskAssignment.campaign_id == campaign_id)
            .all()
        }
        unassigned = [tid for tid in all_ids if tid not in existing]
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        if len(users) != len(set(user_ids)):
            raise ValueError("存在无效 user_id")
        created = 0
        for i, tid in enumerate(unassigned):
            uid = user_ids[i % len(user_ids)]
            db.add(
                LabelingTaskAssignment(
                    campaign_id=campaign_id,
                    task_id=tid,
                    user_id=uid,
                    assigned_by_user_id=assigned_by_user_id,
                    assigned_at=now,
                )
            )
            created += 1
        db.flush()
    return _assign_result(campaign_id, created)


def assign_tasks_explicit(
    campaign_id: str,
    items: list[dict[str, Any]],
    *,
    assigned_by_user_id: int,
) -> dict[str, Any]:
    now = _utcnow()
    all_set = set(list_campaign_task_ids(campaign_id))
    created = 0
    with session_scope() as db:
        existing = {
            r.task_id
            for r in db.query(LabelingTaskAssignment)
            .filter(LabelingTaskAssignment.campaign_id == campaign_id)
            .all()
        }
        for item in items:
            uid = int(item["user_id"])
            user = db.get(User, uid)
            if not user:
                raise ValueError(f"用户不存在: {uid}")
            for tid in item.get("task_ids") or []:
                if tid not in all_set:
                    raise ValueError(f"无效 task_id: {tid}")
                if tid in existing:
                    continue
                db.add(
                    LabelingTaskAssignment(
                        campaign_id=campaign_id,
                        task_id=tid,
                        user_id=uid,
                        assigned_by_user_id=assigned_by_user_id,
                        assigned_at=now,
                    )
                )
                existing.add(tid)
                created += 1
        db.flush()
    return _assign_result(campaign_id, created)


def reassign_task(campaign_id: str, task_id: str, user_id: int) -> dict[str, Any]:
    with session_scope() as db:
        row = (
            db.query(LabelingTaskAssignment)
            .filter(
                LabelingTaskAssignment.campaign_id == campaign_id,
                LabelingTaskAssignment.task_id == task_id,
            )
            .first()
        )
        if not row:
            raise FileNotFoundError("assignment not found")
        user = db.get(User, user_id)
        if not user:
            raise ValueError(f"用户不存在: {user_id}")
        row.user_id = user_id
        db.flush()
        return row.to_dict()


def release_task_assignment(campaign_id: str, task_id: str) -> dict[str, Any]:
    with session_scope() as db:
        row = (
            db.query(LabelingTaskAssignment)
            .filter(
                LabelingTaskAssignment.campaign_id == campaign_id,
                LabelingTaskAssignment.task_id == task_id,
            )
            .first()
        )
        if not row:
            raise FileNotFoundError("assignment not found")
        db.delete(row)
        db.flush()
    return {"ok": True, "released": task_id}


def assert_can_save_task(campaign_id: str, task_id: str, user: User) -> None:
    if user_is_coordinator(user):
        return
    codes = user_role_codes(user)
    if "vendor_labeler" in codes:
        return
    with session_scope() as db:
        row = (
            db.query(LabelingTaskAssignment)
            .filter(
                LabelingTaskAssignment.campaign_id == campaign_id,
                LabelingTaskAssignment.task_id == task_id,
            )
            .first()
        )
        if not row:
            raise PermissionError("该图未分配给您，请联系协调员分包")
        if row.user_id != user.id:
            raise PermissionError("该图已分配给其他标注员")


def mark_task_completed(campaign_id: str, task_id: str, user_id: int) -> None:
    now = _utcnow()
    with session_scope() as db:
        row = (
            db.query(LabelingTaskAssignment)
            .filter(
                LabelingTaskAssignment.campaign_id == campaign_id,
                LabelingTaskAssignment.task_id == task_id,
            )
            .first()
        )
        if row and not row.completed_at:
            row.completed_at = now
            row.completed_by_user_id = user_id

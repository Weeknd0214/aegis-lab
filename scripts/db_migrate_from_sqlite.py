#!/usr/bin/env python3
"""将 SQLite 遗留库 manifests/platform.db 迁移到 PostgreSQL。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform"))

from sqlalchemy import create_engine
from sqlalchemy.orm import joinedload, sessionmaker

from as_platform.config import DATABASE_URL, IS_POSTGRES, SQLITE_LEGACY_PATH
from as_platform.db.engine import Base
from as_platform.db.init_db import init_database
from as_platform.db.models import Approval, Job, Permission, Role, User


def main() -> None:
    if not IS_POSTGRES:
        print("目标 AS_DATABASE_URL 须为 postgresql://…", file=sys.stderr)
        sys.exit(1)
    if not SQLITE_LEGACY_PATH.is_file():
        print(f"无 SQLite 文件: {SQLITE_LEGACY_PATH}，跳过")
        init_database()
        return

    sqlite_url = f"sqlite:///{SQLITE_LEGACY_PATH}"
    src = create_engine(sqlite_url, future=True)
    dst = create_engine(DATABASE_URL, future=True)
    SrcSession = sessionmaker(bind=src)
    DstSession = sessionmaker(bind=dst)

    Base.metadata.create_all(bind=dst)

    with DstSession() as db:
        if db.query(User).count() > 0:
            print("PostgreSQL 已有数据，跳过迁移（可加 --force 清空后重迁）")
            if "--force" not in sys.argv:
                return
            print("清空目标库…")
            db.query(Job).delete()
            db.query(Approval).delete()
            from as_platform.db.models import role_permissions, user_roles
            db.execute(user_roles.delete())
            db.execute(role_permissions.delete())
            db.query(User).delete()
            db.query(Role).delete()
            db.query(Permission).delete()
            db.commit()

    order = [Permission, Role, User, Approval, Job]
    with SrcSession() as sdb, DstSession() as ddb:
        perm_map = {p.id: p for p in sdb.query(Permission).all()}
        for p in perm_map.values():
            ddb.merge(Permission(id=p.id, code=p.code, name=p.name))
        ddb.flush()
        for r in sdb.query(Role).options(joinedload(Role.permissions)).all():
            nr = Role(id=r.id, code=r.code, name=r.name)
            ddb.add(nr)
            ddb.flush()
            nr.permissions = [ddb.get(Permission, p.id) for p in r.permissions]
        for u in sdb.query(User).options(joinedload(User.roles)).all():
            nu = User(
                id=u.id,
                feishu_open_id=u.feishu_open_id,
                feishu_union_id=u.feishu_union_id,
                name=u.name,
                email=u.email,
                avatar_url=u.avatar_url,
                is_active=bool(u.is_active),
                created_at=u.created_at,
                updated_at=u.updated_at,
            )
            ddb.add(nu)
            ddb.flush()
            nu.roles = [ddb.get(Role, r.id) for r in u.roles]
        for a in sdb.query(Approval).all():
            ddb.merge(Approval(
                id=a.id, status=a.status, action=a.action, action_label=a.action_label,
                params_json=a.params_json, note=a.note,
                submitted_by_user_id=a.submitted_by_user_id, submitted_by_name=a.submitted_by_name,
                submitted_at=a.submitted_at, reviewed_by_user_id=a.reviewed_by_user_id,
                reviewed_by_name=a.reviewed_by_name, reviewed_at=a.reviewed_at,
                review_comment=a.review_comment, job_id=a.job_id,
                executed_at=a.executed_at, result_json=a.result_json,
            ))
        for j in sdb.query(Job).all():
            ddb.merge(Job(
                id=j.id, status=j.status, action=j.action, params_json=j.params_json,
                approval_id=j.approval_id, created_at=j.created_at,
                started_at=j.started_at, finished_at=j.finished_at, result_json=j.result_json,
            ))
        ddb.commit()
    print("迁移完成 → PostgreSQL")


if __name__ == "__main__":
    main()

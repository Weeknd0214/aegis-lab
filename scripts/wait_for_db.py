#!/usr/bin/env python3
"""等待 PostgreSQL + Redis 就绪。"""
from __future__ import annotations

import os
import sys
import time

from as_platform.config import IS_POSTGRES, JOB_EXECUTOR, REDIS_URL
from as_platform.db.engine import check_connection
from as_platform.redis.bus import ping_redis


def main() -> None:
    ok_db = True
    if IS_POSTGRES:
        ok_db = False
        for i in range(30):
            if check_connection():
                ok_db = True
                print("PostgreSQL 已就绪")
                break
            print(f"等待 PostgreSQL… ({i + 1}/30)")
            time.sleep(2)
    else:
        if check_connection():
            print("数据库已就绪")
        else:
            print("数据库连接失败", file=sys.stderr)
            sys.exit(1)

    redis_required = JOB_EXECUTOR == "worker" or os.environ.get("AS_REQUIRE_REDIS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if not REDIS_URL:
        print("Redis 未配置，跳过")
        if not ok_db:
            sys.exit(1)
        return

    for i in range(30):
        if ping_redis():
            print("Redis 已就绪")
            break
        print(f"等待 Redis… ({i + 1}/30)")
        time.sleep(2)
    else:
        if redis_required:
            print("Redis 连接超时", file=sys.stderr)
            sys.exit(1)
        print("警告: Redis 不可用，thread 模式仍可启动")

    if not ok_db:
        print("PostgreSQL 连接超时", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

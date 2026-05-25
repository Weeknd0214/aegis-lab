#!/usr/bin/env python3
"""Job Worker：从 Redis 队列取任务并执行（GPU/训练机可单独跑此脚本）。"""
from __future__ import annotations

import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform"))

from as_platform.config import JOB_EXECUTOR, JOB_QUEUE_KEY, REDIS_URL
from as_platform.jobs.queue import _run_job
from as_platform.redis.bus import ping_redis, pop_job

_running = True


def _stop(*_):
    global _running
    _running = False


def main() -> None:
    if JOB_EXECUTOR != "worker":
        print(f"AS_JOB_EXECUTOR={JOB_EXECUTOR}，worker 脚本建议设为 worker", file=sys.stderr)
    if not ping_redis():
        print(f"Redis 不可用: {REDIS_URL}", file=sys.stderr)
        sys.exit(1)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(f"Worker 监听队列 {JOB_QUEUE_KEY} …")

    while _running:
        job_id = pop_job(timeout=3)
        if job_id:
            print(f"执行 Job {job_id}")
            _run_job(job_id)


if __name__ == "__main__":
    main()

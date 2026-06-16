"""批次索引：列表走 DB，重建走扫盘。"""
from __future__ import annotations

import time

from as_platform.labeling.batch_index import (
    index_is_empty,
    list_batches_from_index,
    rebuild_batch_index,
)
from as_platform.labeling.service import list_labeling_batches


def test_rebuild_and_list_from_index():
    r = rebuild_batch_index()
    assert r["ok"] is True
    assert r["count"] >= 0

    t0 = time.perf_counter()
    out = list_batches_from_index(limit=100)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert out["source"] == "index"
    assert "items" in out
    assert elapsed_ms < 500, f"index list too slow: {elapsed_ms:.0f}ms"


def test_list_labeling_batches_uses_index():
    if index_is_empty():
        rebuild_batch_index()
    t0 = time.perf_counter()
    out = list_labeling_batches(limit=50)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert "items" in out
    assert elapsed_ms < 800, f"list_labeling_batches too slow: {elapsed_ms:.0f}ms"


def test_archive_batch_hides_from_list():
    from as_platform.db.engine import session_scope
    from as_platform.db.models import BatchIndex
    from as_platform.labeling.batch_index import archive_batch, list_batches_from_index

    with session_scope() as db:
        rec = (
            db.query(BatchIndex)
            .filter(BatchIndex.archived.is_(False), BatchIndex.stage == "raw_pool")
            .first()
        )
        if not rec:
            return
        cid = rec.campaign_id

    archive_batch(cid)
    out = list_batches_from_index(stage="raw_pool", limit=500)
    assert all(r.get("campaign_id") != cid for r in out["items"])

"""标注批次 stage 读时归一化（兼容旧 pipeline）。"""
from __future__ import annotations

STAGE_ALIASES: dict[str, str] = {
    "review_approved": "labeling_submitted",
}

CANONICAL_STAGES = (
    "raw_pool",
    "out_for_labeling",
    "in_review",
    "review_rejected",
    "labeling_submitted",
    "returned",
    "ingested",
)


def effective_stage(stage: str | None) -> str | None:
    if not stage:
        return stage
    return STAGE_ALIASES.get(stage, stage)


def matches_stage_filter(batch_stage: str | None, filter_stage: str | None) -> bool:
    if not filter_stage:
        return True
    eff = effective_stage(batch_stage)
    return eff == filter_stage or batch_stage == filter_stage

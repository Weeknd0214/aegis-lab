#!/usr/bin/env python3
"""对照 DATA_LAKE_CHECKLIST 阶段 A～E，输出 HSAP 当前实现缺口（只读审计）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform"))

from as_platform.config import WORKSPACE  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"item": name, "ok": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    staging = WORKSPACE / "lake" / "staging"
    reports = WORKSPACE / "manifests" / "lake" / "reports"
    curated = WORKSPACE / "lake" / "curated"

    checks.append(_check("A_staging_dir", staging.is_dir(), str(staging)))
    checks.append(
        _check(
            "A_upload_api",
            (ROOT / "platform/as_platform/data/lake.py").is_file(),
            "analyze_uploaded_candidate / promote",
        )
    )
    checks.append(
        _check(
            "B_analyze_job",
            (ROOT / "platform/as_platform/jobs/runner.py").is_file(),
            "analyze_uploaded_dataset action",
        )
    )
    checks.append(_check("B_reports_dir", reports.is_dir(), str(reports)))
    report_files = list(reports.glob("*.json")) if reports.is_dir() else []
    checks.append(_check("B_sample_report", len(report_files) > 0, f"count={len(report_files)}"))

    checks.append(
        _check(
            "C_approval_flow",
            (ROOT / "platform/as_platform/audit/queue.py").is_file(),
            "delivery_ingest + approvals",
        )
    )
    checks.append(
        _check(
            "D_curated_dir",
            True,
            "optional until first promote" + ("" if curated.is_dir() else f" (missing {curated})"),
        )
    )
    checks.append(
        _check(
            "D_catalog_api",
            (ROOT / "platform/as_platform/api/server.py").is_file(),
            "GET /api/v1/catalog/*",
        )
    )

    failed = [c for c in checks if not c["ok"]]
    out = {"workspace": str(WORKSPACE), "checks": checks, "failed_count": len(failed)}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if failed:
        print("\nLAKE_CHECKLIST_GAPS:", file=sys.stderr)
        for c in failed:
            print(f"  - {c['item']}: {c['detail']}", file=sys.stderr)
        return 1
    print("LAKE_CHECKLIST_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

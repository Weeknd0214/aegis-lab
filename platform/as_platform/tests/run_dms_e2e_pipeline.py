#!/usr/bin/env python3
"""DMS 2 图 E2E：标完后自动 提交→质检→导出→build 入库。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def campaign_id(project: str, task: str, mode: str | None, batch: str, location: str = "inbox") -> str:
    from as_platform.labeling.scope import format_scope_key

    sk = format_scope_key(project, task, mode)
    raw = f"{sk}:{batch}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


class ApiClient:
    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            raise RuntimeError(f"{method} {path} -> {e.code}: {detail}") from e

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, body: dict | None = None) -> Any:
        return self._request("POST", path, body)


def login(base: str, name: str = "e2e-runner") -> ApiClient:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/auth/dev/login",
        data=json.dumps({"name": name}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return ApiClient(base, data["access_token"])


def wait_job(api: ApiClient, job_id: str, timeout: int = 180) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = api.get(f"/api/v1/jobs/{job_id}")
        st = job.get("status")
        if st in ("succeeded", "failed"):
            return job
        time.sleep(1)
    raise TimeoutError(f"job {job_id} not finished in {timeout}s")


def labeled_count(batch_dir: Path) -> int:
    ann_dir = batch_dir / "labels" / "ls_annotations"
    if not ann_dir.is_dir():
        return 0
    from as_platform.labeling.progress import _annotation_has_result

    n = 0
    for p in ann_dir.glob("*.json"):
        if _annotation_has_result(p):
            n += 1
    return n


def batch_stage(batch_dir: Path) -> str:
    meta = batch_dir / "batch.meta.yaml"
    if not meta.is_file():
        return "raw_pool"
    import yaml

    data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    return str(data.get("stage") or "raw_pool")


def cmd_info(args: argparse.Namespace) -> None:
    cid = campaign_id(args.project, args.task, None, args.batch)
    print(f"campaign_id={cid}")
    print(f"annotate_url=/labeling/annotate/{cid}")
    print(f"batch_path=datasets/dms/inbox/{args.task}/{args.batch}")
    wf_root = ROOT / "datasets" / "dms"
    batch_dir = wf_root / "inbox" / args.task / args.batch
    if batch_dir.is_dir():
        print(f"stage={batch_stage(batch_dir)} labeled={labeled_count(batch_dir)}")
    try:
        api = login(args.api)
        row = next(
            (i for i in api.get("/api/v1/labeling/batches?limit=100").get("items", [])
             if i.get("batch") == args.batch and i.get("task") == args.task),
            None,
        )
        if row:
            print(f"platform_stage={row.get('stage')} status={row.get('campaign_status')}")
            print(f"progress={row.get('completed_tasks', '?')}/{row.get('total_tasks', '?')}")
    except Exception as e:
        print(f"api_skip={e}")


def cmd_setup(args: argparse.Namespace) -> None:
    api = login(args.api)
    body = {
        "project": args.project,
        "task": args.task,
        "batch": args.batch,
        "location": "inbox",
    }
    row = api.post("/api/v1/labeling/campaigns/open", body)
    print(json.dumps({"campaign_id": row.get("id"), "stage": row.get("stage"), "cvat_task_id": row.get("cvat_task_id")}, ensure_ascii=False))


def wait_labels(batch_dir: Path, min_images: int, wait_sec: int) -> None:
    if labeled_count(batch_dir) >= min_images:
        return
    if wait_sec <= 0:
        raise RuntimeError(
            f"仅标注 {labeled_count(batch_dir)}/{min_images} 张，请先在平台画框保存，再执行 run 或 run-wait"
        )
    print(f"等待标注 {min_images} 张 (最多 {wait_sec}s)...")
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        n = labeled_count(batch_dir)
        if n >= min_images:
            print(f"labeled={n}")
            return
        time.sleep(3)
    raise TimeoutError(f"超时：仅 {labeled_count(batch_dir)}/{min_images} 张有标注")


def cmd_run(args: argparse.Namespace) -> None:
    cid = campaign_id(args.project, args.task, None, args.batch)
    batch_dir = ROOT / "datasets" / "dms" / "inbox" / args.task / args.batch
    if not batch_dir.is_dir():
        raise FileNotFoundError(batch_dir)

    wait_labels(batch_dir, args.min_images, args.wait_label_sec)
    api = login(args.api)

    print("==> 1. 提交质检")
    api.post(f"/api/v1/labeling/campaigns/{cid}/submit")
    row = next(
        i for i in api.get("/api/v1/labeling/batches?limit=100").get("items", [])
        if i.get("campaign_id") == cid
    )
    assert row.get("stage") == "in_review", row

    print("==> 2. 质检通过 (全部 good)")
    queue = api.get(f"/api/v1/labeling/campaigns/{cid}/review-queue?limit=50")
    items = queue.get("items") or []
    scores = [{"image_path": it["image_path"], "score": "good"} for it in items]
    res = api.post(
        f"/api/v1/labeling/campaigns/{cid}/review-submit",
        {"scores": scores},
    )
    print("review", res)
    row = next(
        i for i in api.get("/api/v1/labeling/batches?limit=100").get("items", [])
        if i.get("campaign_id") == cid
    )
    assert row.get("stage") == "labeling_submitted", row

    print("==> 3. 执行导出")
    exp = api.post(f"/api/v1/labeling/campaigns/{cid}/export")
    job_id = (exp.get("job") or {}).get("id")
    assert job_id, exp
    job = wait_job(api, job_id)
    if job.get("status") != "succeeded":
        raise RuntimeError(f"export failed: {job}")
    print("export_job", job.get("result"))

    row = next(
        i for i in api.get("/api/v1/labeling/batches?limit=100").get("items", [])
        if i.get("campaign_id") == cid
    )
    assert row.get("stage") == "returned", row
    yolo = list((batch_dir / "labels").rglob("*.txt"))
    assert yolo, "export 后应有 YOLO txt"

    print("==> 4. 提交 build 审核")
    appr = api.post(
        "/api/v1/system/audit/submit-build-batch",
        {
            "project": args.project,
            "task": args.task,
            "batch": args.batch,
            "pack": args.pack,
            "location": "inbox",
            "note": f"E2E smoke {args.batch}",
        },
    )
    approval_id = appr.get("id")
    assert approval_id, appr
    print("approval_id", approval_id)

    print("==> 5. 批准 build")
    done = api.post(f"/api/v1/system/audit/{approval_id}/approve", {"comment": "e2e auto approve"})
    build_job_id = done.get("job_id")
    if build_job_id:
        bjob = wait_job(api, build_job_id, timeout=300)
        if bjob.get("status") != "succeeded":
            raise RuntimeError(f"build failed: {bjob}")
        print("build_job", bjob.get("result"))

    row = next(
        i for i in api.get("/api/v1/labeling/batches?limit=100").get("items", [])
        if i.get("campaign_id") == cid
    )
    assert row.get("stage") == "ingested", row
    assert batch_stage(batch_dir) == "ingested", batch_stage(batch_dir)

    dest = ROOT / "datasets" / "dms" / "packs" / args.pack / args.task / "sources" / args.batch
    assert dest.is_dir(), f"missing pack source: {dest}"
    dest_labels = list(dest.rglob("labels/**/*.txt")) + list(dest.rglob("labels/*.txt"))
    assert dest_labels, f"pack 内应有 labels: {dest}"

    print("DMS_E2E_PIPELINE_OK")
    print(json.dumps({
        "campaign_id": cid,
        "batch": args.batch,
        "pack": args.pack,
        "dest": str(dest),
        "yolo_in_inbox": len(yolo),
        "stage": row.get("stage"),
    }, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("setup", "run", "info"))
    ap.add_argument("--api", default="http://127.0.0.1:8787")
    ap.add_argument("--project", default="dms")
    ap.add_argument("--task", default="addw")
    ap.add_argument("--batch", default="e2e_2img_20260616")
    ap.add_argument("--pack", default="dms_v1")
    ap.add_argument("--min-images", type=int, default=2)
    ap.add_argument("--wait-label-sec", type=int, default=0)
    ap.add_argument("--skip-files", action="store_true")
    args = ap.parse_args()

    if args.command == "info":
        cmd_info(args)
    elif args.command == "setup":
        cmd_setup(args)
    elif args.command == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()

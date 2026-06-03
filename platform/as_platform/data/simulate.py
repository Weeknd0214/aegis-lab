"""世界模型仿真数据生成 — API 接口层。

实际生成逻辑由外部世界模型引擎完成（通过 subprocess / HTTP 调用）。
本模块提供：任务提交、队列管理、状态追踪、结果入库。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from as_platform.config import WORKSPACE
from as_platform.db.engine import session_scope

SIM_JOBS_DIR = WORKSPACE / "manifests" / "simulation_jobs"
SIM_OUTPUT_ROOT = WORKSPACE / "datasets" / "dms" / "simulated"

SCENE_TEMPLATES = {
    "urban_highway": {"label": "城市快速路", "desc": "多车道高速公路场景"},
    "urban_street": {"label": "城市街道", "desc": "有交通灯和路口的城市道路"},
    "rural_road": {"label": "乡村道路", "desc": "双车道乡村公路"},
    "tunnel": {"label": "隧道", "desc": "隧道内光照变化场景"},
    "night_city": {"label": "夜间城市", "desc": "低光照城市道路"},
    "rain_highway": {"label": "雨天高速", "desc": "雨天湿滑路面"},
    "fog_rural": {"label": "雾天乡村", "desc": "大雾低能见度"},
}

CAMERA_PRESETS = {
    "truck_front": {"label": "卡车前视", "height": 2.5, "fov": 75, "pitch": -5},
    "truck_side": {"label": "卡车侧视", "height": 2.5, "fov": 100, "pitch": 0},
    "car_front": {"label": "轿车前视", "height": 1.2, "fov": 60, "pitch": -3},
    "car_wide": {"label": "轿车广角", "height": 1.2, "fov": 120, "pitch": 0},
}

OBJECT_CLASSES = ["Pedestrain", "Car", "Truck", "Bus", "Motor-vehicles", "Tricycle", "cones"]


def list_jobs(offset: int = 0, limit: int = 20) -> dict[str, Any]:
    SIM_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for f in sorted(SIM_JOBS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            data["_id"] = f.stem
            if data.get("status") != "archived":
                jobs.append(data)
        except Exception:
            pass
    total = len(jobs)
    return {"items": jobs[offset:offset + limit], "total": total}


def submit_job(params: dict[str, Any], user_name: str = "") -> dict[str, Any]:
    job_id = f"sim-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    scene = params.get("scene", "urban_highway")
    camera = params.get("camera", "truck_front")
    weather = params.get("weather", "clear")
    objects = params.get("objects", OBJECT_CLASSES[:4])
    density = params.get("density", "medium")
    count = min(params.get("count", 100), 5000)
    note = params.get("note", "")
    fov_variant = params.get("fov_variant", False)  # 是否生成多FOV变体

    scene_info = SCENE_TEMPLATES.get(scene, {"label": scene})
    cam_info = CAMERA_PRESETS.get(camera, {"label": camera})

    job = {
        "id": job_id,
        "status": "queued",
        "created_at": now,
        "submitted_by": user_name,
        "params": {
            "scene": scene,
            "scene_label": scene_info["label"],
            "camera": camera,
            "camera_label": cam_info["label"],
            "camera_height": cam_info.get("height", 2.5),
            "camera_fov": cam_info.get("fov", 75),
            "weather": weather,
            "objects": objects,
            "density": density,
            "count": count,
            "fov_variant": fov_variant,
            "note": note,
        },
        "result": None,
        "batch_registered": False,
    }

    SIM_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (SIM_JOBS_DIR / f"{job_id}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))

    # Queue actual generation (mock for now — replace with real world model call)
    _trigger_generation(job_id)

    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    f = SIM_JOBS_DIR / f"{job_id}.json"
    if not f.is_file():
        return None
    data = json.loads(f.read_text())
    data["_id"] = f.stem
    return data


def get_job_images(job_id: str, offset: int = 0, limit: int = 60) -> dict[str, Any]:
    out_dir = SIM_OUTPUT_ROOT / job_id / "images"
    if not out_dir.is_dir():
        return {"items": [], "total": 0}
    imgs = sorted(out_dir.glob("*.jpg")) + sorted(out_dir.glob("*.png"))
    total = len(imgs)
    page = imgs[offset:offset + limit]
    return {
        "items": [{"name": p.name, "path": str(p.relative_to(SIM_OUTPUT_ROOT))} for p in page],
        "total": total,
    }


def ingest_job_to_batch(job_id: str, task: str = "adas", user_name: str = "") -> dict[str, Any]:
    """将仿真生成的数据注册为批次，直接入库。"""
    job = get_job(job_id)
    if not job:
        return {"ok": False, "error": "Job not found"}

    out_dir = SIM_OUTPUT_ROOT / job_id
    if not out_dir.is_dir():
        return {"ok": False, "error": "生成数据不存在"}

    # Register as batch
    from as_platform.data.core import register_batch
    batch_name = f"sim_{job_id}"
    try:
        register_batch(None, "dms", task, batch_name, stage="returned", location="inbox")
        # Update job status
        job["status"] = "ingested"
        job["batch_registered"] = True
        job["batch_name"] = batch_name
        (SIM_JOBS_DIR / f"{job_id}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
        return {"ok": True, "batch": batch_name, "task": task}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _trigger_generation(job_id: str) -> None:
    """触发实际生成（当前为 mock）。替换为真实世界模型调用。"""
    import threading

    def _run():
        try:
            # TODO: 替换为真实世界模型调用
            # 例如: subprocess.run(["python", "world_model/generate.py", "--job", job_id])
            _update_status(job_id, "running")
            # Mock: create output directory but no actual images
            out_dir = SIM_OUTPUT_ROOT / job_id / "images"
            out_dir.mkdir(parents=True, exist_ok=True)
            # Mock 完成
            _update_status(job_id, "completed")
        except Exception as e:
            _update_status(job_id, "failed", str(e))

    threading.Thread(target=_run, daemon=True, name=f"sim-{job_id}").start()


def _update_status(job_id: str, status: str, error: str = "") -> None:
    f = SIM_JOBS_DIR / f"{job_id}.json"
    if f.is_file():
        data = json.loads(f.read_text())
        data["status"] = status
        if error:
            data["error"] = error
        if status == "completed":
            data["completed_at"] = datetime.now(timezone.utc).isoformat()
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2))

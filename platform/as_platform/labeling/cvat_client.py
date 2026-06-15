"""CVAT 标注引擎客户端：通过 REST API 管理 Task/Job，上传数据，拉取标注结果。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── 配置 ──────────────────────────────────────────────
# CVAT_HOST: 容器内 REST API 地址（HSAP 后端调用，无需 CVAT 账号）
# CVAT_PUBLIC_URL: 浏览器 iframe 嵌入地址（标注画布，用户只通过 HSAP 进入）
_CVAT_HOST = os.environ.get("CVAT_HOST", "http://cvat_traefik:8080")
_CVAT_PUBLIC_URL = os.environ.get("CVAT_PUBLIC_URL", "http://127.0.0.1:8080").rstrip("/")
_CVAT_EXTRA_HEADERS = {"Host": "localhost"}  # traefik host-based routing for internal Docker access


def public_job_url(task_id: int, job_id: int) -> str:
    """浏览器可访问的标注页 URL（由 HSAP iframe 嵌入，不暴露 CVAT 账号体系）。"""
    return f"{_CVAT_PUBLIC_URL}/tasks/{task_id}/jobs/{job_id}"


def public_job_url_with_frame(job_url: str, frame_index: int) -> str:
    """在 CVAT Job URL 上附加帧索引，用于定位到指定图片。"""
    if frame_index < 0:
        return job_url
    sep = "&" if "?" in job_url else "?"
    return f"{job_url}{sep}frame={frame_index}"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.cvat+json; version=2.0"})
    s.headers.update(_CVAT_EXTRA_HEADERS)
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[429, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


@dataclass
class CVATTask:
    id: int
    name: str
    status: str
    url: str
    job_url: str | None = None
    job_id: int | None = None


class CVATClient:
    """封装 CVAT REST API，提供创建任务、上传数据、拉取标注等功能。"""

    def __init__(self, host: str | None = None):
        self.host = (host or _CVAT_HOST).rstrip("/")
        self._session = _session()
        self._api = f"{self.host}/api"

    # ── 健康检查 ───────────────────────────────────────

    def ping(self) -> bool:
        try:
            r = self._session.get(f"{self._api}/tasks?page_size=1", timeout=5)
            return 200 <= r.status_code < 400
        except Exception:
            return False

    # ── Task CRUD ──────────────────────────────────────

    def create_task(
        self,
        name: str,
        labels: list[dict[str, Any]],
        *,
        project_id: int | None = None,
        subset: str | None = None,
        bug_tracker: str | None = None,
    ) -> CVATTask:
        """创建 CVAT Task（带标注标签定义）。"""
        payload: dict[str, Any] = {
            "name": name,
            "labels": labels,
        }
        if project_id:
            payload["project_id"] = project_id
        if subset:
            payload["subset"] = subset
        if bug_tracker:
            payload["bug_tracker"] = bug_tracker

        r = self._session.post(f"{self._api}/tasks", json=payload)
        r.raise_for_status()
        data = r.json()
        return CVATTask(id=data["id"], name=data["name"], status=data.get("status", ""), url=data.get("url", ""))

    def _resolve_job(self, data: dict, task_id: int) -> tuple[int | None, str | None]:
        jobs = data.get("jobs") or {}
        if isinstance(jobs, list):
            if jobs:
                jid = jobs[0].get("id")
                return jid, public_job_url(task_id, jid)
        elif isinstance(jobs, dict):
            count = jobs.get("count", 0)
            if count > 0:
                job_url = f"{self._api}/jobs?task_id={task_id}"
                jr = self._session.get(job_url)
                jr.raise_for_status()
                jresults = jr.json().get("results", [])
                if jresults:
                    jid = jresults[0].get("id")
                    return jid, public_job_url(task_id, jid)
        return None, None

    def get_task(self, task_id: int) -> CVATTask:
        r = self._session.get(f"{self._api}/tasks/{task_id}")
        r.raise_for_status()
        data = r.json()
        job_id, job_url = self._resolve_job(data, task_id)
        return CVATTask(id=data["id"], name=data["name"], status=data.get("status", ""), url=data.get("url", ""), job_url=job_url, job_id=job_id)

    def list_tasks(self, *, status: str | None = None, name: str | None = None) -> list[CVATTask]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if name:
            params["search"] = name
        r = self._session.get(f"{self._api}/tasks", params=params)
        r.raise_for_status()
        results = r.json().get("results", [])
        tasks = []
        for data in results:
            job_id, job_url = self._resolve_job(data, data["id"])
            tasks.append(CVATTask(id=data["id"], name=data["name"], status=data.get("status", ""), url=data.get("url", ""), job_url=job_url, job_id=job_id))
        return tasks

    def delete_task(self, task_id: int) -> None:
        r = self._session.delete(f"{self._api}/tasks/{task_id}")
        r.raise_for_status()

    def get_task_status(self, task_id: int) -> str:
        return self.get_task(task_id).status

    # ── 数据上传 ───────────────────────────────────────

    def upload_images(self, task_id: int, image_paths: list[Path]) -> None:
        """将图片文件上传到指定 Task。"""
        # CVAT Data API: POST /api/tasks/{id}/data
        files = {}
        opened: list = []
        for i, p in enumerate(image_paths):
            if not p.is_file():
                continue
            f = open(p, "rb")
            opened.append(f)
            files[f"client_files[{i}]"] = (p.name, f, "image/jpeg")
        try:
            r = self._session.post(f"{self._api}/tasks/{task_id}/data", files=files, data={"image_quality": 70})
            r.raise_for_status()
        finally:
            for f in opened:
                f.close()

    def upload_annotations(self, task_id: int, annotation_file: Path, fmt: str = "KITTI 1.0") -> None:
        """上传已有标注（如 KITTI 格式的 label_2）。"""
        with open(annotation_file, "rb") as f:
            r = self._session.put(
                f"{self._api}/tasks/{task_id}/annotations",
                files={"annotation_file": (annotation_file.name, f)},
                data={"format": fmt},
            )
            r.raise_for_status()

    # ── 标注拉取 ───────────────────────────────────────

    def download_annotations(self, task_id: int, fmt: str = "KITTI 1.0") -> bytes:
        """下载标注结果，返回原始字节。"""
        r = self._session.get(f"{self._api}/tasks/{task_id}/annotations", params={"format": fmt})
        r.raise_for_status()
        return r.content

    def download_annotations_json(self, task_id: int) -> dict[str, Any]:
        """拉取 Job 级标注 JSON（CVAT 2.x 已废弃 task 级 export GET）。"""
        task = self.get_task(task_id)
        if not task.job_id:
            raise ValueError(f"CVAT task {task_id} 尚无 Job，请等待数据上传完成")
        return self.get_job_annotations(task.job_id)

    def get_job_annotations(self, job_id: int) -> dict[str, Any]:
        r = self._session.get(f"{self._api}/jobs/{job_id}/annotations")
        r.raise_for_status()
        return r.json()

    def get_job_data_meta(self, job_id: int) -> dict[str, Any]:
        r = self._session.get(f"{self._api}/jobs/{job_id}/data/meta")
        r.raise_for_status()
        return r.json()

    def get_job_label_map(self, job_id: int) -> dict[int, str]:
        r = self._session.get(f"{self._api}/labels", params={"job_id": job_id})
        r.raise_for_status()
        return {lb["id"]: lb["name"] for lb in r.json().get("results", [])}

    # ── Job 管理 ───────────────────────────────────────

    def get_job_url(self, task_id: int, job_index: int = 0) -> str | None:
        """获取可用于 iframe 嵌入的 Job URL。"""
        task = self.get_task(task_id)
        return task.job_url

    def get_job_status(self, task_id: int) -> str:
        task = self.get_task(task_id)
        return task.status

    # ── 3D Cuboid 标注 ─────────────────────────────────

    def upload_cuboid_xml(self, task_id: int, xml_content: str) -> None:
        """上传 3D cuboid 标注（CVAT for images 1.1 XML 格式）。"""
        import io
        r = self._session.post(
            f"{self._api}/tasks/{task_id}/annotations?format=CVAT+1.1",
            files={"annotation_file": ("annotations.xml", io.BytesIO(xml_content.encode()), "application/xml")},
        )
        r.raise_for_status()
        return r.json()

    # ── Project 管理（可选） ────────────────────────────

    def create_project(self, name: str, labels: list[dict[str, Any]]) -> dict[str, Any]:
        r = self._session.post(f"{self._api}/projects", json={"name": name, "labels": labels})
        r.raise_for_status()
        return r.json()

    def list_projects(self) -> list[dict[str, Any]]:
        r = self._session.get(f"{self._api}/projects")
        r.raise_for_status()
        return r.json().get("results", [])


# ── 全局客户端实例 ────────────────────────────────────

_client: CVATClient | None = None


def get_cvat_client() -> CVATClient:
    global _client
    if _client is None:
        _client = CVATClient()
    return _client

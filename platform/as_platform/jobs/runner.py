"""执行动作：优先引擎适配器，fallback as.py CLI。"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from as_platform.config import WORKSPACE, PLATFORM_DIR, LANE_DATA_VIZ_ENABLED

if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

ML_PY = WORKSPACE / "as.py"
AS_PY = ML_PY

LONG_ACTIONS = {"train_dms", "train_lane", "pipeline_dms", "eval_dms", "eval_lane", "visualize_dms", "visualize_lane"}


def _auto_snapshot(project: str, task: str = "") -> None:
    """build 成功后自动创建数据集版本快照。"""
    try:
        from as_platform.data.versions import create_snapshot
        desc = f"自动快照 · build {project}"
        if task:
            desc += f"/{task}"
        create_snapshot(project, description=desc, author="system")
    except Exception:
        pass  # 快照失败不影响 build


def _run_ml(argv: list[str], timeout: int = 7200) -> dict[str, Any]:
    cmd = [sys.executable, str(ML_PY), *argv]
    proc = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"as.py 失败 (exit {proc.returncode}):\n{proc.stderr or proc.stdout}")
    return {"ok": True, "stdout": proc.stdout, "stderr": proc.stderr, "command": " ".join(cmd)}


def execute_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    p = params or {}

    if action == "train_dms":
        track = p.get("track", "platform")
        if track == "local":
            from algorithms.dms_yolo.adapter import train_local
            return train_local(
                p["task"],
                p.get("mode", "full"),
                p.get("config_overrides"),
                submode=p.get("submode"),
            )
        from algorithms.dms_yolo.adapter import train_platform
        return train_platform(p["task"], p.get("mode", "full"), submode=p.get("submode"))

    if action == "train_lane":
        track = p.get("track", "platform")
        if track == "local":
            from algorithms.lane_ufld.adapter import train_local
            return train_local(p.get("config_overrides"))
        from algorithms.lane_ufld.adapter import train_platform
        return train_platform()

    if action == "train_dms_legacy":
        argv = ["train", "dms", p["task"]]
        if p.get("mode"):
            argv.extend(["--mode", str(p["mode"])])
        return _run_ml(argv, timeout=86400)

    if action == "train_lane_legacy":
        return _run_ml(["train", "lane"], timeout=86400)

    if action == "build_dms":
        argv = ["build", "dms", p["task"]]
        if p.get("pack"):
            argv.extend(["--pack", str(p["pack"])])
        if p.get("batch"):
            argv.extend(["--batch", str(p["batch"])])
        if p.get("all_sources"):
            argv.append("--all-sources")
        if p.get("dry_run"):
            argv.append("--dry-run")
        if p.get("skip_validate"):
            argv.append("--skip-validate")
        if p.get("no_refresh"):
            argv.append("--no-refresh")
        result = _run_ml(argv)
        # 自动创建数据集快照
        _auto_snapshot("dms", task=p.get("task", ""))
        return result

    if action == "build_lane":
        result = _run_ml(["build", "lane"])
        _auto_snapshot("lane")
        return result

    if action == "enable_pack":
        return _run_ml(["enable", p["project"], p["pack"]])

    if action == "disable_pack":
        return _run_ml(["disable", p["project"], p["pack"]])

    if action == "eval_dms":
        argv = ["eval", "dms", p["task"]]
        if p.get("save_candidate"):
            argv.append("--save-candidate")
        if p.get("weights"):
            argv.extend(["--weights", str(p["weights"])])
        return _run_ml(argv, timeout=3600)

    if action == "eval_lane":
        from algorithms.lane_ufld.adapter import eval_task

        return eval_task(
            model_path=p.get("model_path"),
            data_root=p.get("data_root"),
            test_list=p.get("test_list", "list/test_gt.txt"),
        )

    if action == "visualize_dms":
        from algorithms.dms_yolo.adapter import visualize_task

        return visualize_task(
            p["task"],
            weights=p.get("weights"),
        )

    if action == "visualize_lane":
        if not LANE_DATA_VIZ_ENABLED:
            raise RuntimeError("车道线数据可视化暂未开放")
        from algorithms.lane_ufld.adapter import visualize_task

        return visualize_task(
            model_path=p.get("model_path"),
            data_root=p.get("data_root"),
            test_list=p.get("test_list", "list/test_gt.txt"),
        )

    if action == "promote_dms":
        argv = ["promote", "dms", p["task"]]
        if p.get("force"):
            argv.append("--force")
        return _run_ml(argv)

    if action == "pipeline_dms":
        argv = ["pipeline", "dms", p["task"], "--pack", str(p.get("pack", "dms_v2"))]
        if p.get("batch"):
            argv.extend(["--batch", str(p["batch"])])
        if p.get("all_sources"):
            argv.append("--all-sources")
        if p.get("train"):
            argv.append("--train")
        if p.get("dry_run"):
            argv.append("--dry-run")
        return _run_ml(argv, timeout=86400)

    if action == "register_batch":
        from as_platform.data.core import register_batch

        register_batch(
            None, p["project"], p.get("task"), p["batch"],
            pack=p.get("pack"), stage=p.get("stage", "returned"),
            engineer=p.get("engineer"), location=p.get("location", "inbox"),
        )
        return {"ok": True, "stdout": "register_batch ok", "stderr": ""}

    if action == "delivery_ingest":
        from as_platform.integrations.delivery_ingest import run_delivery_ingest

        delivery_id = p.get("delivery_id") or ""
        if not delivery_id:
            raise ValueError("缺少 delivery_id")
        result = run_delivery_ingest(delivery_id)
        return {
            "ok": True,
            "stdout": json.dumps(result, ensure_ascii=False),
            "stderr": "",
            "result": result,
        }

    if action == "analyze_uploaded_dataset":
        from as_platform.data.lake import analyze_uploaded_candidate

        candidate_id = p["candidate_id"]
        result = analyze_uploaded_candidate(candidate_id)
        return {
            "ok": True,
            "stdout": json.dumps(result, ensure_ascii=False),
            "stderr": "",
            "result": result,
        }

    if action == "labeling_export":
        from as_platform.db.engine import session_scope
        from as_platform.db.models import LabelingCampaign
        from as_platform.labeling.annotate import resolve_campaign_batch_dir
        from as_platform.labeling.service import get_campaign

        campaign_id = p.get("campaign_id", "")
        row = get_campaign(campaign_id)
        if not row:
            raise ValueError("campaign not found")
        task = row.get("task") or "dam"
        batch = row.get("batch") or ""
        pack = row.get("pack") or "dms_v2"
        export = row.get("export_default") or "yolo"
        if row.get("project") == "dms" and export in ("yolo", "yolo_pose") and batch:
            scripts_dir = WORKSPACE / "datasets" / "dms" / "scripts"
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            from export_ls_to_yolo import export_batch

            with session_scope() as db:
                camp = db.get(LabelingCampaign, campaign_id)
                if not camp:
                    raise ValueError("campaign not found")
                batch_dir = resolve_campaign_batch_dir(camp)
            export_mode = "pose" if export == "yolo_pose" else "detect"
            conv = export_batch(
                batch_dir,
                task,
                mode=export_mode,
                task_mode=row.get("mode"),
            )
            if conv.get("written", 0) == 0:
                raise ValueError(
                    "export_ls_to_yolo: 无有效标注可导出 (written=0); "
                    f"skipped_empty={conv.get('skipped_empty')} missing_ann={conv.get('missing_ann')}"
                )
            argv = ["build", "dms", task, "--pack", pack, "--batch", batch]
            result = _run_ml(argv)
            result["export_convert"] = conv
            return result
        if row.get("project") == "lane" and export == "lane_gt_txt":
            scripts_dir = WORKSPACE / "datasets" / "lane" / "scripts"
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            from export_ls_to_lane_gt import export_batch

            with session_scope() as db:
                camp = db.get(LabelingCampaign, campaign_id)
                if not camp:
                    raise ValueError("campaign not found")
                batch_dir = resolve_campaign_batch_dir(camp)
            conv = export_batch(batch_dir)
            if conv.get("written", 0) == 0:
                raise ValueError(
                    "export_ls_to_lane_gt: 无有效标注可导出 (written=0); "
                    f"skipped_empty={conv.get('skipped_empty')} missing_ann={conv.get('missing_ann')}"
                )
            argv = ["build", "lane"]
            result = _run_ml(argv)
            result["export_convert"] = conv
            return result
        return {
            "ok": True,
            "stdout": json.dumps({"export": export, "campaign": row}, ensure_ascii=False),
            "stderr": "",
            "message": f"export 类型 {export} 暂无 CLI，已记录",
        }

    if action == "labeling_ml_predict":
        raise ValueError("labeling_ml_predict 已停用")

    raise ValueError(f"未实现执行: {action}")

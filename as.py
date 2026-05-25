#!/usr/bin/env python3
"""HSAP 工作流 CLI（Huaxu Sentinel Active Safety Platform）：add → build → train（dms + lane）。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

WORKSPACE = Path(__file__).resolve().parent
_PLATFORM = WORKSPACE / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))


def load_wf() -> dict:
    return yaml.safe_load((WORKSPACE / "workflow.registry.yaml").read_text(encoding="utf-8"))


def save_wf(wf: dict) -> None:
    (WORKSPACE / "workflow.registry.yaml").write_text(
        yaml.dump(wf, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def proj_root(wf: dict, name: str) -> Path:
    rel = wf["projects"][name]["root"]
    return (WORKSPACE / rel).resolve()


def train_workdir(wf: dict, project: str) -> Path:
    rel = wf["projects"][project]["train"]["workdir"]
    return (WORKSPACE / rel).resolve()


def load_pack_registry(project: str, root: Path, wf: dict) -> dict:
    pcfg = wf["projects"][project]
    reg_file = root / pcfg.get("packs_registry", "datasets_registry.json")
    if reg_file.suffix in (".yaml", ".yml"):
        return yaml.safe_load(reg_file.read_text(encoding="utf-8"))
    return json.loads(reg_file.read_text(encoding="utf-8"))


def resolve_pack(project: str, root: Path, wf: dict, name: str) -> str:
    """解析包名 -> 相对 root 的目录路径（用于 lane 的 active_packs 与 dms）。"""
    reg = load_pack_registry(project, root, wf)
    name = reg.get("aliases", {}).get(name, name)
    for p in reg.get("packs", []):
        if p.get("name") == name:
            return p.get("path", name)
    if (root / name).is_dir():
        return name
    known = [p.get("name") for p in reg.get("packs", [])]
    sys.exit(f"[{project}] 未知包: {name}，已登记: {known}")


def resolve_pack_dir(project: str, root: Path, wf: dict, name: str) -> Path:
    return (root / resolve_pack(project, root, wf, name)).resolve()


def cmd_status(wf: dict) -> None:
    print(f"workspace: {WORKSPACE}")
    for pname, pcfg in wf["projects"].items():
        root = proj_root(wf, pname)
        active = pcfg.get("active_packs", [])
        print(f"\n[{pname}] {root}")
        print(f"  训练启用: {active}")

        if pname == "dms":
            reg = yaml.safe_load((root / pcfg["registry"]).read_text(encoding="utf-8"))
            src_sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
            for task, tcfg in reg.get("tasks", {}).items():
                inbox = root / "inbox" / task
                pending_inbox = [d.name for d in inbox.iterdir() if d.is_dir()] if inbox.is_dir() else []
                pending_by_pack = []
                for pack in active:
                    try:
                        pack_dir = resolve_pack_dir("dms", root, wf, pack)
                    except SystemExit:
                        continue
                    src_root = pack_dir / tcfg["task_dir"] / src_sub
                    if src_root.is_dir():
                        batches = [
                            d.name for d in src_root.iterdir()
                            if d.is_dir() and d.name not in ("_ingested", "_merged")
                            and not d.name.startswith(".")
                        ]
                        if batches:
                            pending_by_pack.append(f"{pack}:{batches}")
                print(f"  {task}: inbox={pending_inbox or '空'}  sources={pending_by_pack or '空'}")

        if pname == "lane":
            reg = load_pack_registry("lane", root, wf)
            for pack_name in active:
                path = resolve_pack("lane", root, wf, pack_name)
                lp = root / path / "list" / "train_gt.txt"
                n = sum(1 for _ in lp.open()) if lp.is_file() else 0
                print(f"  {pack_name} ({path}): train={n}")


def ensure_dms_pack(root: Path, pack_name: str) -> None:
    """新包自动登记到 data_packs.yaml 并创建 packs/<name>/。"""
    reg_path = root / "data_packs.yaml"
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    names = {p["name"] for p in reg.get("packs", [])}
    if pack_name not in names:
        path = f"packs/{pack_name}"
        reg.setdefault("packs", []).append({"name": pack_name, "path": path, "role": "incremental"})
        reg_path.write_text(
            yaml.dump(reg, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        print(f"已登记数据包: {pack_name}")
    (root / "packs" / pack_name).mkdir(parents=True, exist_ok=True)


def cmd_add_dms(
    wf: dict,
    task: str,
    src: Path,
    batch: str | None,
    copy: bool,
    into: str,
    pack: str,
) -> None:
    root = proj_root(wf, "dms")
    reg = yaml.safe_load((root / wf["projects"]["dms"]["registry"]).read_text(encoding="utf-8"))
    if task not in reg.get("tasks", {}):
        sys.exit(f"未知 task: {task}")
    ensure_dms_pack(root, pack)
    tcfg = reg["tasks"][task]
    pack_dir = resolve_pack_dir("dms", root, wf, pack)
    task_dir = pack_dir / tcfg["task_dir"]
    task_dir.mkdir(parents=True, exist_ok=True)

    batch = batch or datetime.now().strftime("%Y%m%d_%H%M")

    if into == "sources":
        src_sub = (reg.get("ingest") or {}).get("sources_subdir", "sources")
        dst = task_dir / src_sub / batch
        if dst.exists() and any(dst.iterdir()):
            sys.exit(f"sources 已存在且非空: {dst}")
        dst.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            for name in ("images", "labels", "train"):
                s = src / name
                if s.exists():
                    (dst / name).symlink_to(s.resolve(), target_is_directory=s.is_dir())
            if not any(dst.iterdir()):
                (dst / "_src").symlink_to(src.resolve())
        print(f"pack={pack} sources: {dst}")
        print(f"下一步: python as.py build dms {task} --pack {pack} --all-sources")
        print(f"训练前: python as.py enable dms {pack}  # 若尚未加入 active_packs")
        return

    dst = root / "inbox" / task / batch
    if dst.exists() and any(dst.iterdir()):
        sys.exit(f"inbox 已存在且非空: {dst}")
    dst.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        for name in ("images", "labels", "train"):
            s = src / name
            if s.exists():
                (dst / name).symlink_to(s.resolve(), target_is_directory=s.is_dir())
        if not any(dst.iterdir()):
            (dst / "_src").symlink_to(src.resolve())
    print(f"inbox: {dst}")
    print(f"下一步: python as.py build dms {task} --pack {pack} --batch {batch}")


def cmd_refresh_dms(wf: dict, task: str | None) -> None:
    root = proj_root(wf, "dms")
    cmd = [sys.executable, str(root / "scripts" / "refresh_yaml.py")]
    if task:
        cmd.extend(["--task", task])
    subprocess.check_call(cmd, cwd=root)


def run_validate_dms(task: str | None = None) -> None:
    cmd = [sys.executable, str(WORKSPACE / "scripts" / "validate_dms_tasks.py")]
    if task:
        cmd.extend(["--task", task])
    subprocess.check_call(cmd)


def _read_jsonl_tail(path: Path, n: int = 5) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def cmd_pending(wf: dict, as_json: bool) -> None:
    """待处理：inbox/sources、批次 meta、未 enable 的包。"""
    from as_platform.sdk import get_pending_report

    report = get_pending_report(wf)

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"workspace: {WORKSPACE}")
    for pname, proj in report["projects"].items():
        print(f"\n[{pname}]")
        print(f"  active_packs: {proj['active_packs']}")
        if proj.get("not_enabled"):
            print(f"  未参与训练: {proj['not_enabled']}")
        if pname == "dms":
            for task, info in proj.get("tasks", {}).items():
                print(f"  {task}: inbox={info['inbox'] or '空'} sources={info['sources'] or '空'}")
            if proj.get("recent_ingest"):
                last = proj["recent_ingest"][-1]
                print(f"  最近 ingest: task={last.get('task')} pack={last.get('pack')} ts={last.get('ts')}")
    pending_batches = [b for b in report.get("batches", []) if b.get("stage") in ("returned", "raw_pool", "out_for_labeling")]
    if pending_batches:
        print(f"\n  批次详情 ({len(pending_batches)}):")
        for b in pending_batches[:8]:
            print(f"    {b.get('task') or b.get('pack')}/{b.get('batch')}: {b.get('stage')} @ {b.get('location')}")


def cmd_register_batch(
    wf: dict,
    project: str,
    task: str | None,
    batch: str,
    pack: str | None,
    stage: str,
    engineer: str | None,
    location: str,
) -> None:
    from as_platform.sdk import register_batch

    result = register_batch(
        wf, project, task, batch,
        pack=pack, stage=stage, engineer=engineer, location=location,
    )
    print(f"已写入: {result['meta_path']}")
    b = result["batch"]
    print(f"  stage={b.get('stage')} images={b.get('counts', {}).get('images')} labels={b.get('counts', {}).get('labels')}")
    print(f"  下一步: {b.get('next_cli')}")


def cmd_build_dms(
    wf: dict,
    task: str | None,
    pack: str,
    batch: str | None,
    dry_run: bool,
    refresh: bool,
    all_sources: bool,
    skip_validate: bool,
) -> None:
    root = proj_root(wf, "dms")
    scripts = root / "scripts"

    if not task:
        cmd_refresh_dms(wf, None)
        print("已按 active_packs 生成 manifests/yaml_active/*.yaml（未合并任何新文件）")
        return

    ensure_dms_pack(root, pack)
    scripts = root / "scripts"

    if all_sources:
        cmd = [
            sys.executable,
            str(scripts / "ingest_incremental.py"),
            "--task", task,
            "--pack", pack,
            "--all-sources",
        ]
    elif batch:
        src = root / "inbox" / task / batch
        if not src.is_dir():
            sys.exit(f"inbox 批次不存在: {src}")
        cmd = [
            sys.executable,
            str(scripts / "ingest_incremental.py"),
            "--task", task,
            "--pack", pack,
            "--src", str(src),
        ]
    else:
        cmd = [
            sys.executable,
            str(scripts / "ingest_incremental.py"),
            "--task", task,
            "--pack", pack,
            "--all-inbox",
        ]
    if dry_run:
        cmd.append("--dry-run")
    subprocess.check_call(cmd, cwd=root)

    if dry_run:
        return

    if not skip_validate:
        print("validate …")
        run_validate_dms(task)

    if refresh:
        cmd_refresh_dms(wf, task)
    else:
        print("提示: python as.py build dms --refresh  # 生成训练 yaml")


def cmd_eval_dms(wf: dict, task: str, weights: Path | None, save_candidate: bool) -> None:
    cmd = [sys.executable, str(WORKSPACE / "scripts" / "eval_dms.py"), task]
    if weights:
        cmd.extend(["--weights", str(weights)])
    if save_candidate:
        cmd.append("--save-candidate")
    subprocess.check_call(cmd)


def cmd_promote_dms(wf: dict, task: str, force: bool) -> None:
    root = proj_root(wf, "dms")
    versions = yaml.safe_load((root / "manifests" / "train_versions.yaml").read_text())
    if task not in versions:
        sys.exit(f"未知 task: {task}")

    tv = versions[task]
    candidate = tv.get("candidate")
    last_eval = tv.get("last_eval")

    auto = wf.get("automation") or {}
    if auto.get("require_eval_before_promote", True) and not last_eval and not force:
        sys.exit("无 last_eval，请先 python as.py eval dms {task} 或 --force")

    if not candidate:
        sys.exit("candidate 为空，请先 train 后 eval --save-candidate")

    if last_eval and not force:
        min_delta = float(auto.get("min_delta_map50", -1.0))
        delta = last_eval.get("delta_map50")
        if delta is not None and delta < min_delta:
            sys.exit(f"eval delta_map50={delta} < {min_delta}，拒绝 promote")

    tv["current"] = candidate
    versions[task] = tv
    (root / "manifests" / "train_versions.yaml").write_text(
        yaml.dump(versions, allow_unicode=True, sort_keys=False), encoding="utf-8",
    )
    print(f"promoted {task}: current = {candidate}")


def cmd_pipeline_dms(
    wf: dict,
    task: str,
    pack: str,
    batch: str | None,
    all_sources: bool,
    do_train: bool,
    dry_run: bool,
) -> None:
    steps = ["build(ingest+validate+refresh)"]
    if do_train:
        steps.extend(["train", "eval", "promote?"])
    print(f"pipeline dms {task} pack={pack} dry_run={dry_run}: {' → '.join(steps)}")
    if dry_run:
        return
    cmd_build_dms(wf, task, pack, batch, False, True, all_sources, False)
    if do_train:
        cmd_train_dms(wf, task, "full")
        cmd_eval_dms(wf, task, None, True)
        print("若指标过线: python as.py promote dms", task)


def cmd_train_dms(wf: dict, task: str, mode: str, track: str = "platform") -> None:
    if track == "local":
        from algorithms.dms_yolo.adapter import train_local

        result = train_local(task, mode)
        print(f"local train 完成: {result.get('run_dir')}")
        print("local 轨不更新 train_versions candidate")
        return

    from algorithms.dms_yolo.adapter import train_platform

    result = train_platform(task, mode)
    print(f"platform train 完成, candidate={result.get('candidate')}")
    print(f"下一步: python as.py eval dms {task} && python as.py promote dms {task}")


def cmd_add_lane(wf: dict, src: Path, engineer: str, date: str, copy: bool, pack: str | None) -> None:
    root = proj_root(wf, "lane")
    date_digits = re.sub(r"[^0-9]", "", date)
    pack_path = f"DATASET-AddBy-{engineer}-{date_digits}"
    pack_name = pack or f"lane_{engineer}_{date_digits}"

    cmd = [
        sys.executable,
        str(root / "scripts" / "build_ufld_pack.py"),
        "--src", str(src.resolve()),
        "--parent", str(root),
        "--engineer", engineer,
        "--date", date,
    ]
    if copy:
        cmd.append("--copy")
    subprocess.check_call(cmd)

    reg_path = root / wf["projects"]["lane"]["packs_registry"]
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    if not any(p.get("name") == pack_name for p in reg.get("packs", [])):
        reg.setdefault("packs", []).append({
            "name": pack_name,
            "path": pack_path,
            "role": "incremental",
        })
        reg.setdefault("aliases", {})[pack_name] = pack_path
        reg_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"已登记包: {pack_name} -> {pack_path}")

    print(f"下一步: python as.py enable lane {pack_name}")
    print(f"         python as.py build lane && python as.py train lane")


def cmd_build_lane(wf: dict) -> None:
    root = proj_root(wf, "lane")
    pcfg = wf["projects"]["lane"]
    packs = [resolve_pack("lane", root, wf, x) for x in pcfg.get("active_packs", [])]
    script = root / "scripts" / "merge_ufld_lists.py"
    merge = pcfg["merge"]

    train_inputs = [f"{pk}/list/train_gt.txt" for pk in packs]
    val_inputs = [f"{pk}/list/val_gt.txt" for pk in packs if (root / pk / "list" / "val_gt.txt").is_file()]

    cmd = [
        sys.executable, str(script),
        "--data-root", str(root),
        "--prefix-from-pack",
        "--out", merge["train"],
        "--update-registry",
        "--base", train_inputs[0],
        *train_inputs[1:],
    ]
    subprocess.check_call(cmd, cwd=root)

    if val_inputs:
        subprocess.check_call([
            sys.executable, str(script),
            "--data-root", str(root),
            "--prefix-from-pack",
            "--out", merge["val"],
            *val_inputs,
        ], cwd=root)

    sync_ufld_config(wf, pcfg.get("active_packs", []))
    print(f"合并训练列表（active_packs）: {packs}")
    print(f"  {root / merge['train']}")


def sync_ufld_config(wf: dict, pack_names: list[str]) -> None:
    pcfg = wf["projects"]["lane"]
    cfg_path = train_workdir(wf, "lane") / pcfg["train"]["config"]
    if not cfg_path.is_file():
        print(f"跳过 config: {cfg_path}")
        return
    root = proj_root(wf, "lane")
    text = cfg_path.read_text(encoding="utf-8")
    text = re.sub(r"^data_root\s*=\s*['\"].*?['\"]", f"data_root = '{root}'", text, count=1, flags=re.M)
    packs_repr = ",\n    ".join(f"'{p}'" for p in pack_names)
    text = re.sub(r"train_packs\s*=\s*\[[^\]]*\]", f"train_packs = [\n    {packs_repr},\n]", text, count=1, flags=re.S)
    text = re.sub(r"^remerge_train_list\s*=\s*\w+", "remerge_train_list = True", text, count=1, flags=re.M)
    cfg_path.write_text(text, encoding="utf-8")
    print(f"sync → {cfg_path}")


def cmd_train_lane(wf: dict, track: str = "platform") -> None:
    if track == "local":
        from algorithms.lane_ufld.adapter import train_local

        result = train_local()
        print(f"local lane train: {result.get('workdir')}")
        return
    from algorithms.lane_ufld.adapter import train_platform

    train_platform()
    print("platform lane train 完成")


def cmd_enable(wf: dict, project: str, pack: str) -> None:
    pcfg = wf["projects"][project]
    root = proj_root(wf, project)
    real_name = pack
    resolve_pack(project, root, wf, pack)
    packs = pcfg.setdefault("active_packs", [])
    if real_name not in packs:
        packs.append(real_name)
        save_wf(wf)
    print(f"[{project}] active_packs: {packs}")
    print("下一步: python as.py build", project, "# 生成合并训练配置")


def cmd_disable(wf: dict, project: str, pack: str) -> None:
    pcfg = wf["projects"][project]
    root = proj_root(wf, project)
    resolve_pack(project, root, wf, pack)
    base = pcfg.get("base_pack", "dms_v1")
    if pack == base:
        sys.exit(f"不能 disable 基线包: {base}")
    packs = pcfg.get("active_packs", [])
    if pack in packs:
        packs.remove(pack)
        save_wf(wf)
    print(f"[{project}] active_packs: {packs}")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"ML 工作区 {WORKSPACE}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status")
    pe = sub.add_parser("pending")
    pe.add_argument("--json", action="store_true")

    ad = sub.add_parser("add")
    ad.add_argument("project", choices=("dms", "lane"))
    ad.add_argument("task", nargs="?")
    ad.add_argument("--src", type=Path, required=True)
    ad.add_argument("--batch")
    ad.add_argument("--pack", help="dms/lane 目标数据包名，如 dms_v2 / lane_v1")
    ad.add_argument("--engineer")
    ad.add_argument("--date")
    ad.add_argument("--into", choices=("inbox", "sources"), default="inbox")
    ad.add_argument("--copy", action="store_true")

    bd = sub.add_parser("build")
    bd.add_argument("project", choices=("dms", "lane"))
    bd.add_argument("task", nargs="?")
    bd.add_argument("--pack", default="dms_v1", help="dms 写入/合并的目标包")
    bd.add_argument("--batch")
    bd.add_argument("--dry-run", action="store_true")
    bd.add_argument("--all-sources", action="store_true")
    bd.add_argument("--no-refresh", action="store_true")
    bd.add_argument("--skip-validate", action="store_true")

    ev = sub.add_parser("eval")
    ev.add_argument("project", choices=("dms",))
    ev.add_argument("task")
    ev.add_argument("--weights", type=Path)
    ev.add_argument("--save-candidate", action="store_true")

    pr = sub.add_parser("promote")
    pr.add_argument("project", choices=("dms",))
    pr.add_argument("task")
    pr.add_argument("--force", action="store_true")

    pl = sub.add_parser("pipeline")
    pl.add_argument("project", choices=("dms",))
    pl.add_argument("task")
    pl.add_argument("--pack", default="dms_v2")
    pl.add_argument("--batch")
    pl.add_argument("--all-sources", action="store_true")
    pl.add_argument("--train", action="store_true", help="build 后继续 train+eval")
    pl.add_argument("--dry-run", action="store_true")

    tr = sub.add_parser("train")
    tr.add_argument("project", choices=("dms", "lane"))
    tr.add_argument("task", nargs="?")
    tr.add_argument("--mode", default="full", choices=("full", "continue"))
    tr.add_argument("--track", default="platform", choices=("local", "platform"),
                    help="local=研发直训; platform=yaml_active+晋级链")

    en = sub.add_parser("enable")
    en.add_argument("project")
    en.add_argument("pack")
    di = sub.add_parser("disable")
    di.add_argument("project")
    di.add_argument("pack")

    rb = sub.add_parser("register-batch", help="写入 batch.meta.yaml（不移动文件）")
    rb.add_argument("project", choices=("dms", "lane"))
    rb.add_argument("task", nargs="?")
    rb.add_argument("batch", help="批次目录名")
    rb.add_argument("--pack")
    rb.add_argument("--stage", default="returned",
                    choices=("raw_pool", "out_for_labeling", "returned", "ingested"))
    rb.add_argument("--engineer")
    rb.add_argument("--location", default="inbox", choices=("inbox", "sources", "pack", "unregistered"))

    args = ap.parse_args()
    wf = load_wf()

    if args.cmd == "status":
        cmd_status(wf)
    elif args.cmd == "pending":
        cmd_pending(wf, args.json)
    elif args.cmd == "add":
        if args.project == "dms":
            if not args.task:
                sys.exit("dms add 需要 task")
            pack = args.pack or "dms_v2"
            if pack == "dms_v1":
                print("提示: 增量通常写入 dms_v2+，勿覆盖基线 dms_v1")
            cmd_add_dms(wf, args.task, args.src, args.batch, args.copy, args.into, pack)
        else:
            if not args.engineer or not args.date:
                sys.exit("lane add 需要 --engineer --date")
            cmd_add_lane(wf, args.src, args.engineer, args.date, args.copy, args.pack)
    elif args.cmd == "build":
        if args.project == "dms":
            cmd_build_dms(
                wf,
                args.task,
                args.pack,
                args.batch,
                args.dry_run,
                not args.no_refresh,
                args.all_sources,
                getattr(args, "skip_validate", False),
            )
        else:
            cmd_build_lane(wf)
    elif args.cmd == "eval":
        if args.project == "dms":
            cmd_eval_dms(wf, args.task, args.weights, args.save_candidate)
    elif args.cmd == "promote":
        if args.project == "dms":
            cmd_promote_dms(wf, args.task, args.force)
    elif args.cmd == "pipeline":
        if args.project == "dms":
            cmd_pipeline_dms(
                wf, args.task, args.pack, args.batch,
                args.all_sources, args.train, args.dry_run,
            )
    elif args.cmd == "train":
        if args.project == "dms":
            if not args.task:
                sys.exit("dms train 需要 task")
            if args.track == "platform":
                plat = wf.get("platform", {}).get("training", {}).get("tracks", {})
                if plat.get("platform_require_audit", True):
                    print("提示: 平台轨训练建议经 API 审核: POST /api/v1/approvals/submit")
            cmd_train_dms(wf, args.task, args.mode, args.track)
        else:
            cmd_train_lane(wf, args.track)
    elif args.cmd == "enable":
        cmd_enable(wf, args.project, args.pack)
    elif args.cmd == "disable":
        cmd_disable(wf, args.project, args.pack)
    elif args.cmd == "register-batch":
        if not args.batch:
            sys.exit("register-batch 需要 batch 名")
        cmd_register_batch(
            wf, args.project, args.task, args.batch,
            args.pack, args.stage, args.engineer, args.location,
        )


if __name__ == "__main__":
    main()

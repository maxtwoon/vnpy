#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Provenance: vendored from D:\repo\ashare\skills\sync-guardian\scripts\handoff.py
# on 2026-07-12 for A42 sync-guardian hardening. This copy is now authoritative
# for the vnpy repo; divergence from the external source is expected and acceptable.
"""handoff.py — 多 agent 交接驱动器（与 sync_check.py 同放 tools/）

两种任务模式（.synccheck.yml handoff 段）：
  file: HANDOFF.md      单任务：仓库根一个交接文件
  dir:  handoffs/       多任务并行：目录下每个 <task-id>.md 一个任务（配 --task 定位）

命令：
  python tools/handoff.py list                                 # 任务清单（dir 模式）
  python tools/handoff.py new <task-id> --title "..." [--fast]  # 建任务；--fast 跳过 design（小任务快车道）
  python tools/handoff.py status [--task <id>]
  python tools/handoff.py next --actor <owner> --summary "..." [--task <id>]    # 推进（事务式：写入→门禁→不过回滚）
  python tools/handoff.py reject --actor <owner> --to dev --reason "..."        # 打回（须命中 reject_from 白名单）
  python tools/handoff.py fix --actor <owner> --reason "..."                    # 微循环：review 中的小修，不重置阶段
  python tools/handoff.py run [--once] [--timeout 3600]          # 自动流水线：逐阶段调 agent 命令
    · 未配置 command 的阶段视为人工阶段（如 plan-review 审批）：run 干净停下（exit 0）并给出处理指引
    · no_auto_advance 清单内的阶段（如 review）agent 必须显式 next/reject，不作为时 run 报错中止

健壮性与通知：
  run 每条 agent 命令有超时；全程事件追加写 .handoff_run.log；
  配置 handoff.webhook_env 后，打回/门禁拦截/流水线完成会推送通知（钉钉/企业微信 text 格式）。
"""
from __future__ import annotations
import argparse
import datetime
import json
import os
import re
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        if stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
        else:
            stream.reconfigure(errors="replace")


_configure_stdio()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sync_check import (_load_config, _parse_front_matter, handoff_missing_stage_owners,  # noqa: E402
                        handoff_reject_from, handoff_task_stages, run_checks)

DEFAULT_STAGES = ["design", "dev", "review", "done"]
RUN_LOG = ".handoff_run.log"
BLOCKER_KINDS = {"quota", "auth", "human", "ci", "other"}
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

NEW_TMPL = """---
task: {title}
stage: {stage}
owner: {owner}
updated: {today}
track: {track}
deliverables: []
blockers: []
---

## 背景与目标

{title}

## 验收标准

- [ ] （design 阶段填写；fast 任务由 dev 直接列自测点）

## 给下一棒的说明

（每次交接重写本节：入口、约束、坑）

## 决策记录

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| {today} | 人 → {owner} | → {stage} | 任务创建（{track}） |
"""


def _die(msg: str, code: int = 1) -> None:
    print(f"[HANDOFF][FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def _today() -> str:
    return datetime.date.today().isoformat()


def _log(root: Path, msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n"
    try:
        with (root / RUN_LOG).open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _webhook_url(ho: Dict[str, Any]) -> Optional[str]:
    if not isinstance(ho, dict):
        return None
    env_name = ho.get("webhook_env")
    if env_name:
        return os.environ.get(str(env_name))
    return ho.get("webhook")


def _notify(ho: Dict[str, Any], text: str) -> None:
    """best-effort webhook 推送（钉钉/企业微信通用 text 格式），失败不阻塞流程。"""
    url = _webhook_url(ho)
    if not url:
        return
    try:
        payload = json.dumps({"msgtype": "text", "text": {"content": f"[sync-guardian] {text}"}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:  # noqa: BLE001
        print("[HANDOFF][WARN] webhook 通知失败（不影响流程）", file=sys.stderr)


def _run_command(cmd: str, root: Path, timeout: int, env: Dict[str, str]) -> Optional[int]:
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    preexec_fn = None if os.name == "nt" else os.setsid
    proc = subprocess.Popen(cmd, shell=True, cwd=root, env=env,
                            creationflags=creationflags, preexec_fn=preexec_fn)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGKILL)
        return None


def _agent_env(base: Dict[str, str], fp: Path, fm: Dict[str, Any], root: Path) -> Dict[str, str]:
    rel = fp.relative_to(root).as_posix()
    env = dict(base)
    env.update({
        "SYNC_GUARDIAN_ACTOR": str(fm.get("owner", "")),
        "SYNC_GUARDIAN_TASK_ID": fp.stem,
        "SYNC_GUARDIAN_HANDOFF_FILE": rel,
        "SYNC_GUARDIAN_STAGE": str(fm.get("stage", "")),
        "SYNC_GUARDIAN_TRACK": str(fm.get("track", "full")),
    })
    return env


# ------------------------------------------------------------ state io
def _cfg_ho(root: Path, config: Optional[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    cfg, _ = _load_config(root, config)
    ho = cfg.get("handoff") or {}
    if isinstance(ho, str):
        ho = {"file": ho}
    if not ho or not (ho.get("file") or ho.get("dir")):
        _die("配置缺 handoff 段（.synccheck.yml 配置 handoff.file 或 handoff.dir）", 2)
    return cfg, ho


def _task_files(root: Path, ho: Dict[str, Any]) -> List[Path]:
    if ho.get("dir"):
        d = root / ho["dir"]
        return sorted(d.glob("*.md")) if d.exists() else []
    return [root / ho["file"]]


def _safe_task_id(task: str) -> str:
    value = str(task or "")
    if value in {".", ".."} or not TASK_ID_RE.fullmatch(value):
        _die(f"非法 task id: {value!r}（仅允许 A-Z a-z 0-9 . _ -，且不能包含路径分隔符）", 2)
    return value


def _task_path(root: Path, ho: Dict[str, Any], task: str) -> Path:
    safe = _safe_task_id(task)
    d = (root / ho["dir"]).resolve()
    fp = (d / f"{safe}.md").resolve()
    if fp.parent != d:
        _die(f"非法 task id: {task!r}（任务文件必须位于 {d}）", 2)
    return fp


def _resolve_file(root: Path, ho: Dict[str, Any], task: Optional[str]) -> Path:
    if ho.get("dir"):
        task = task or os.environ.get("SYNC_GUARDIAN_TASK_ID")
        d = root / ho["dir"]
        if task:
            fp = _task_path(root, ho, task)
            if not fp.exists():
                _die(f"任务不存在: {fp}（用 list 查看，new 创建）", 2)
            return fp
        files = _task_files(root, ho)
        active = [f for f in files
                  if (_parse_front_matter(f.read_text(encoding="utf-8")) or {}).get("stage") != "done"]
        pick = active or files
        if len(pick) == 1:
            return pick[0]
        if not pick:
            _die("暂无任务；先用 handoff.py new <id> 创建任务", 2)
        _die("多任务模式需 --task <id> 定位（用 list 查看任务）", 2)
    fp = root / ho["file"]
    if not fp.exists():
        _die(f"交接文件不存在: {fp}（从 templates/HANDOFF.md 拷一份）", 2)
    return fp


def _read(fp: Path) -> Tuple[str, Dict[str, Any]]:
    text = fp.read_text(encoding="utf-8")
    fm = _parse_front_matter(text)
    if fm is None:
        _die(f"{fp.name} 缺 front matter", 2)
    return text, fm


def _task_stages(ho: Dict[str, Any], fm: Dict[str, Any]) -> List[str]:
    """任务实际阶段序列：fast 任务跳过首阶段（design），小任务不付设计流程税。"""
    return handoff_task_stages(ho, fm)


def _require_valid_task_stages(ho: Dict[str, Any], fm: Dict[str, Any]) -> List[str]:
    stages = _task_stages(ho, fm)
    if not stages:
        tracks = list((ho.get("tracks") or {}).keys())
        _die(f"track 非法: {fm.get('track', 'full')!r}（配置的 tracks: {tracks}）", 2)
    missing_owners = handoff_missing_stage_owners(ho, stages)
    if missing_owners:
        _die(f"configured track owner 缺失: {missing_owners}", 2)
    return stages


def _set_key(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"(?m)^({re.escape(key)}:\s*)([^#\n]*?)(\s*#.*)?$")
    new, n = pat.subn(lambda m: f"{m.group(1)}{value}{m.group(3) or ''}", text, count=1)
    if n == 0:
        _die(f"交接文件缺字段 {key}")
    return new


def _set_list_key(text: str, key: str, values: List[str]) -> str:
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:\s*", line):
            start = i
            break
    if start is None:
        _die(f"交接文件缺字段 {key}")

    end = start + 1
    while end < len(lines):
        stripped = lines[end].strip()
        is_top_key = lines[end] and not lines[end].startswith((" ", "\t")) and re.match(r"^[^:\n]+:", lines[end])
        if stripped == "---" or is_top_key:
            break
        end += 1

    replacement = [f"{key}: []\n"] if not values else [f"{key}:\n"] + [f"  - {v}\n" for v in values]
    return "".join(lines[:start] + replacement + lines[end:])


def _blocker_line(kind: str, actor: str, reason: str) -> str:
    return f"{kind} | {actor} | {reason}"


def _require_actor_or_human(ho: Dict[str, Any], fm: Dict[str, Any], actor: str) -> None:
    if actor == "human":
        return
    _require_actor(ho, fm, actor)



def _upsert_key(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"(?m)^({re.escape(key)}:\s*)([^#\n]*?)(\s*#.*)?$")
    new, n = pat.subn(lambda m: f"{m.group(1)}{value}{m.group(3) or ''}", text, count=1)
    if n:
        return new

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        _die("handoff front matter missing; cannot write last_transition")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            lines.insert(i, f"{key}: {value}\n")
            return "".join(lines)
    _die("handoff front matter is not closed; cannot write last_transition")
    return text


def _actor(args) -> str:
    actor = getattr(args, "actor", None) or os.environ.get("SYNC_GUARDIAN_ACTOR")
    if not actor:
        _die("missing actor: pass --actor <owner> or set SYNC_GUARDIAN_ACTOR")
    return actor


def _require_actor(ho: Dict[str, Any], fm: Dict[str, Any], actor: str) -> None:
    stage = fm.get("stage")
    expected = (ho.get("owners") or {}).get(stage)
    if expected and actor != expected:
        _die(f"actor not allowed: stage={stage} requires {expected}, got {actor}")
    if not expected and isinstance((ho.get("tracks") if isinstance(ho, dict) else None), dict) and stage != "done":
        _die(f"configured track owner 缺失: {stage}", 2)


def _require_reject_allowed(ho: Dict[str, Any], fm: Dict[str, Any], to_stage: str) -> None:
    """打回必须命中白名单（定义在 sync_check.handoff_reject_from，门禁与驱动器共用一份）。"""
    stage = fm.get("stage")
    allowed = handoff_reject_from(ho).get(stage, [])
    if to_stage not in allowed:
        _die(f"reject not allowed from stage {stage!r} to {to_stage!r}; allowed targets: {allowed}")

def _append_history(text: str, row: str) -> str:
    if "## 交接历史" not in text:
        text = (text.rstrip() + "\n\n## 交接历史\n\n"
                "| 日期 | 从 → 到 | 阶段变化 | 摘要 |\n|------|---------|----------|------|")
    return text.rstrip() + "\n" + row + "\n"


def _gate(root: Path, cfg: Dict[str, Any]) -> bool:
    errors = run_checks(root, cfg)
    for e in errors:
        print(f"[HANDOFF][GATE] {e}", file=sys.stderr)
    return not errors


def _require_run_transition_valid(root: Path, cfg: Dict[str, Any], fp: Path,
                                  before_fm: Dict[str, Any],
                                  after_fm: Dict[str, Any]) -> None:
    required = [
        "last_transition_actor",
        "last_transition_from_stage",
        "last_transition_to_stage",
        "last_transition_from_owner",
        "last_transition_to_owner",
    ]
    missing = [key for key in required if not after_fm.get(key)]
    if missing:
        _die(f"agent self-handoff missing last_transition metadata: {missing}")
    if after_fm.get("last_transition_from_stage") != before_fm.get("stage"):
        _die("agent self-handoff transition from_stage does not match previous stage")
    if after_fm.get("last_transition_from_owner") != before_fm.get("owner"):
        _die("agent self-handoff transition from_owner does not match previous owner")
    if after_fm.get("last_transition_actor") != before_fm.get("owner"):
        _die("agent self-handoff transition actor must be the previous stage owner")
    if after_fm.get("last_transition_to_stage") != after_fm.get("stage"):
        _die("agent self-handoff transition to_stage does not match current stage")
    if not _gate(root, cfg):
        _log(root, f"GATE-BLOCK {fp.name}")
        _die("agent self-handoff failed gate validation")


def _write_gated(root: Path, cfg: Dict[str, Any], ho: Dict[str, Any], fp: Path,
                 old_text: str, new_text: str, ok_msg: str, use_gate: bool) -> None:
    """事务式写入：写 → 门禁 → 不过回滚并通知。"""
    fp.write_text(new_text, encoding="utf-8")
    if use_gate and not _gate(root, cfg):
        fp.write_text(old_text, encoding="utf-8")
        _log(root, f"GATE-BLOCK {fp.name}")
        _notify(ho, f"门禁拦截：{fp.name} 交接被回滚，需先满足交接 DoD")
        _die("门禁未过，已回滚。先满足交接 DoD 再操作。")
    print(f"[HANDOFF][OK] {ok_msg}")


def _transition(root: Path, cfg: Dict[str, Any], ho: Dict[str, Any], fp: Path, text: str,
                fm: Dict[str, Any], new_stage: str, summary: str, use_gate: bool, actor: str,
                kind: str = "next") -> None:
    owners = ho.get("owners") or {}
    old_stage, old_owner = fm.get("stage", "?"), fm.get("owner", "?")
    new_owner = owners.get(new_stage, old_owner)
    new_text = _set_key(text, "stage", new_stage)
    new_text = _set_key(new_text, "owner", new_owner)
    new_text = _set_key(new_text, "updated", _today())
    new_text = _upsert_key(new_text, "last_transition_kind", kind)
    new_text = _upsert_key(new_text, "last_transition_actor", actor)
    new_text = _upsert_key(new_text, "last_transition_from_stage", old_stage)
    new_text = _upsert_key(new_text, "last_transition_to_stage", new_stage)
    new_text = _upsert_key(new_text, "last_transition_from_owner", old_owner)
    new_text = _upsert_key(new_text, "last_transition_to_owner", new_owner)
    new_text = _append_history(
        new_text, f"| {_today()} | {old_owner} → {new_owner} | {old_stage} → {new_stage} | {summary} |")
    _write_gated(root, cfg, ho, fp, text, new_text,
                 f"{fp.stem}: {old_stage}({old_owner}) → {new_stage}({new_owner})", use_gate)
    _log(root, f"TRANSITION {fp.stem} {old_stage}->{new_stage} {summary}")


# ------------------------------------------------------------ commands
def cmd_list(root: Path, args) -> None:
    _, ho = _cfg_ho(root, args.config)
    files = _task_files(root, ho)
    if not files:
        print("（无任务）")
        return
    print(f"{'任务':<20}{'阶段':<10}{'接棒者':<14}{'track':<7}{'更新':<12}标题")
    for f in files:
        fm = _parse_front_matter(f.read_text(encoding="utf-8")) or {}
        print(f"{f.stem:<20}{fm.get('stage', '?'):<10}{fm.get('owner', '?'):<14}"
              f"{fm.get('track', 'full'):<7}{fm.get('updated', '?'):<12}{fm.get('task', '')}")


def cmd_new(root: Path, args) -> None:
    _, ho = _cfg_ho(root, args.config)
    if not ho.get("dir"):
        _die("new 仅用于多任务模式（配置 handoff.dir）；单文件模式请直接编辑 HANDOFF.md", 2)
    d = root / ho["dir"]
    d.mkdir(parents=True, exist_ok=True)
    fp = _task_path(root, ho, args.id)
    if fp.exists():
        _die(f"任务已存在: {fp}", 2)
    if args.fast and args.track:
        _die("--fast 与 --track 不能同时使用", 2)
    if args.track and not isinstance(ho.get("tracks"), dict):
        _die("--track 需要先在 .synccheck.yml 配置 handoff.tracks；未配置时请使用默认 full 或 --fast", 2)
    track = args.track or ("fast" if args.fast else "full")
    stages = handoff_task_stages(ho, {"track": track})
    if not stages:
        _die(f"track 非法: {track!r}（配置的 tracks: {list((ho.get('tracks') or {}).keys())}）", 2)
    missing_owners = handoff_missing_stage_owners(ho, stages)
    if missing_owners:
        _die(f"configured track owner 缺失: {missing_owners}", 2)
    stage = stages[0]
    owner = (ho.get("owners") or {}).get(stage, "unassigned")
    fp.write_text(NEW_TMPL.format(title=args.title or args.id, stage=stage, owner=owner,
                                  today=_today(), track=track), encoding="utf-8")
    print(f"[HANDOFF][OK] 新任务 {args.id}（{track}，起始阶段 {stage}，接棒者 {owner}）→ {fp}")
    _log(root, f"NEW {args.id} track={track}")


def cmd_status(root: Path, args) -> None:
    _, ho = _cfg_ho(root, args.config)
    if ho.get("dir") and not args.task and not os.environ.get("SYNC_GUARDIAN_TASK_ID"):
        cmd_list(root, args)
        return
    fp = _resolve_file(root, ho, args.task)
    _, fm = _read(fp)
    print(f"task : {fm.get('task')}\nstage: {fm.get('stage')}\nowner: {fm.get('owner')}\n"
          f"track: {fm.get('track', 'full')}\nupdated: {fm.get('updated')}")
    for d in fm.get("deliverables", []) or []:
        mark = "OK " if (root / d).exists() else "缺失"
        print(f"  deliverable [{mark}] {d}")


def cmd_next(root: Path, args) -> None:
    cfg, ho = _cfg_ho(root, args.config)
    fp = _resolve_file(root, ho, args.task)
    text, fm = _read(fp)
    actor = _actor(args)
    _require_actor(ho, fm, actor)
    stages = _require_valid_task_stages(ho, fm)
    cur = fm.get("stage")
    if cur not in stages:
        _die(f"当前 stage 非法: {cur!r}（该任务阶段序列 {stages}）")
    if cur == stages[-1]:
        _die(f"已是最终阶段 {cur}，无可推进")
    _transition(root, cfg, ho, fp, text, fm, stages[stages.index(cur) + 1],
                args.summary or "交接", use_gate=not args.no_gate, actor=actor)


def cmd_reject(root: Path, args) -> None:
    cfg, ho = _cfg_ho(root, args.config)
    fp = _resolve_file(root, ho, args.task)
    text, fm = _read(fp)
    actor = _actor(args)
    stages = _require_valid_task_stages(ho, fm)
    if args.to not in stages:
        _die(f"--to 非法: {args.to}（该任务阶段序列 {stages}）")
    _require_actor(ho, fm, actor)
    _require_reject_allowed(ho, fm, args.to)
    if stages.index(args.to) >= stages.index(fm.get("stage", stages[-1])):
        _die("reject 只能退回更早的阶段")
    _transition(root, cfg, ho, fp, text, fm, args.to, f"打回: {args.reason}", use_gate=False,
                actor=actor, kind="reject")
    _notify(ho, f"打回：{fp.stem} 退回 {args.to}——{args.reason}")
    print("[HANDOFF] 注意：问题清单请写入交接文件的\"给下一棒的说明\"")


def cmd_fix(root: Path, args) -> None:
    """微循环：review 中发现小问题，修复后留痕，不重置阶段、不换 owner——避免全阶段重跑。"""
    cfg, ho = _cfg_ho(root, args.config)
    fp = _resolve_file(root, ho, args.task)
    text, fm = _read(fp)
    actor = _actor(args)
    _require_actor(ho, fm, actor)
    stages = _require_valid_task_stages(ho, fm)
    cur = fm.get("stage")
    if cur in (stages[0], stages[-1]):
        _die(f"fix 微循环用于中间阶段的小修（当前 {cur}）；设计期直接改，done 后走新任务")
    new_text = _set_key(text, "updated", _today())
    new_text = _upsert_key(new_text, "last_transition_kind", "fix")
    new_text = _upsert_key(new_text, "last_transition_actor", actor)
    new_text = _upsert_key(new_text, "last_transition_from_stage", cur)
    new_text = _upsert_key(new_text, "last_transition_to_stage", cur)
    new_text = _upsert_key(new_text, "last_transition_from_owner", fm.get("owner", "?"))
    new_text = _upsert_key(new_text, "last_transition_to_owner", fm.get("owner", "?"))
    new_text = _append_history(
        new_text, f"| {_today()} | {fm.get('owner', '?')} ⟲ | {cur}（微循环） | 微循环修复: {args.reason} |")
    _write_gated(root, cfg, ho, fp, text, new_text,
                 f"{fp.stem}: 微循环修复留痕（阶段保持 {cur}）", use_gate=not args.no_gate)
    _log(root, f"FIX {fp.stem} {args.reason}")


def cmd_block(root: Path, args) -> None:
    cfg, ho = _cfg_ho(root, args.config)
    fp = _resolve_file(root, ho, args.task)
    text, fm = _read(fp)
    actor = _actor(args)
    _require_actor_or_human(ho, fm, actor)
    blockers = list(fm.get("blockers") or [])
    blockers.append(_blocker_line(args.kind, actor, args.reason))
    new_text = _set_key(text, "updated", _today())
    new_text = _set_list_key(new_text, "blockers", blockers)
    new_text = _append_history(
        new_text, f"| {_today()} | {actor} | {fm.get('stage', '?')}（阻塞） | 阻塞: {args.kind} - {args.reason} |")
    _write_gated(root, cfg, ho, fp, text, new_text,
                 f"{fp.stem}: 已记录阻塞（{args.kind}）", use_gate=not args.no_gate)
    _log(root, f"BLOCK {fp.stem} {args.kind} {args.reason}")


def cmd_unblock(root: Path, args) -> None:
    cfg, ho = _cfg_ho(root, args.config)
    fp = _resolve_file(root, ho, args.task)
    text, fm = _read(fp)
    actor = _actor(args)
    _require_actor_or_human(ho, fm, actor)
    new_text = _set_key(text, "updated", _today())
    new_text = _set_list_key(new_text, "blockers", [])
    new_text = _append_history(
        new_text, f"| {_today()} | {actor} | {fm.get('stage', '?')}（解除阻塞） | 解除阻塞: {args.reason} |")
    _write_gated(root, cfg, ho, fp, text, new_text,
                 f"{fp.stem}: 已解除阻塞", use_gate=not args.no_gate)
    _log(root, f"UNBLOCK {fp.stem} {args.reason}")


def cmd_run(root: Path, args) -> None:
    """自动流水线：每阶段调 agent 命令（带超时）；成功后若 agent 未自行交接则代为推进（含门禁）。"""
    max_steps = 12
    for _ in range(max_steps):
        cfg, ho = _cfg_ho(root, args.config)
        fp = _resolve_file(root, ho, args.task)
        text, fm = _read(fp)
        stages = _require_valid_task_stages(ho, fm)
        cur = fm.get("stage")
        if fm.get("blockers"):
            print(f"[HANDOFF] {fp.stem} 存在阻塞项，等待处理。")
            _log(root, f"RUN-BLOCKED {fp.stem}")
            _notify(ho, f"任务阻塞：{fp.stem}（{cur}）")
            return
        if cur == stages[-1]:
            print(f"[HANDOFF][OK] {fp.stem} 已到最终阶段 {cur}，流水线完成。")
            _log(root, f"RUN-DONE {fp.stem}")
            _notify(ho, f"流水线完成：{fp.stem}（{fm.get('task', '')}）")
            return
        cmd = (ho.get("commands") or {}).get(cur)
        if not cmd:
            # 未配置命令的阶段视为人工阶段（如 plan-review 审批）：干净停下等人，exit 0
            owner = fm.get("owner", "?")
            allowed = handoff_reject_from(ho).get(cur, [])
            print(f"[HANDOFF] {fp.stem} 停在阶段 {cur}（接棒者 {owner}）：该阶段未配置自动命令，等待人工处理。")
            print(f"  通过: python tools/handoff.py next --actor {owner} --summary \"{cur} 通过\"")
            if allowed:
                print(f"  打回: python tools/handoff.py reject --actor {owner} "
                      f"--to <{'|'.join(allowed)}> --reason \"...\"")
            print("  处理后重跑 python tools/handoff.py run 继续流水线。")
            _log(root, f"RUN-PAUSE {fp.stem} {cur}")
            _notify(ho, f"等待人工处理：{fp.stem} 停在 {cur}（{owner}）")
            return
        print(f"[HANDOFF] {fp.stem} 阶段 {cur}（{fm.get('owner')}）→ 调用 agent：{cmd}")
        _log(root, f"RUN-STAGE {fp.stem} {cur} cmd={cmd}")
        rc = _run_command(cmd, root, args.timeout, _agent_env(os.environ, fp, fm, root))
        if rc is None:
            _log(root, f"RUN-TIMEOUT {fp.stem} {cur} ({args.timeout}s)")
            _notify(ho, f"超时中止：{fp.stem} 阶段 {cur} 超过 {args.timeout}s")
            _die(f"agent 命令超时（{args.timeout}s），流水线中止（阶段仍为 {cur}）。")
        if rc != 0:
            _log(root, f"RUN-FAIL {fp.stem} {cur} rc={rc}")
            _notify(ho, f"agent 失败：{fp.stem} 阶段 {cur} 退出码 {rc}")
            _die(f"agent 命令退出码 {rc}，流水线中止（阶段仍为 {cur}）。")
        _, fm2 = _read(fp)
        if fm2.get("stage") != cur:
            _require_run_transition_valid(root, cfg, fp, fm, fm2)
            print(f"[HANDOFF] agent 已自行交接：{cur} → {fm2.get('stage')}")
        elif cur in (ho.get("no_auto_advance") or []):
            # 该阶段要求 agent 显式表态（next/reject），不作为不能等于自动通过
            _log(root, f"RUN-NO-DECISION {fp.stem} {cur}")
            _notify(ho, f"无明确结论：{fp.stem} 阶段 {cur} 的 agent 未显式交接（next/reject）")
            _die(f"阶段 {cur} 配置了 no_auto_advance：agent 未显式 next/reject，流水线中止（阶段仍为 {cur}）。")
        else:
            text, fm = _read(fp)  # 重读（agent 可能改了正文）
            _transition(root, cfg, ho, fp, text, fm, stages[stages.index(cur) + 1],
                        f"自动交接（{cur} 阶段 agent 完成）", use_gate=True, actor=str(fm.get("owner", "")))
        if args.once:
            return
    _log(root, "RUN-LOOP-LIMIT")
    _die(f"超过 {max_steps} 步仍未到最终阶段（可能在反复打回），人工介入。")


def main() -> None:
    ap = argparse.ArgumentParser(description="多 agent 交接驱动器")
    ap.add_argument("--root", default=".", help="仓库根")
    ap.add_argument("--config", default=None, help=".synccheck.yml/.json 路径")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="任务清单（多任务模式）")
    p_new = sub.add_parser("new", help="创建任务（多任务模式）")
    p_new.add_argument("id", help="任务 id（文件名）")
    p_new.add_argument("--title", default=None, help="任务标题")
    p_new.add_argument("--fast", action="store_true", help="快车道：跳过 design，适合小任务")
    p_new.add_argument("--track", default=None, help="任务轨道；配置 handoff.tracks 后必须命中其中一个 key")
    p_st = sub.add_parser("status", help="查看状态")
    p_st.add_argument("--task", default=None)
    p_next = sub.add_parser("next", help="推进到下一阶段（事务式，含门禁）")
    p_next.add_argument("--task", default=None)
    p_next.add_argument("--summary", default=None)
    p_next.add_argument("--no-gate", action="store_true")
    p_next.add_argument("--actor", default=None, help="current stage owner; overrides SYNC_GUARDIAN_ACTOR")
    p_rej = sub.add_parser("reject", help="打回到更早阶段")
    p_rej.add_argument("--task", default=None)
    p_rej.add_argument("--to", required=True)
    p_rej.add_argument("--reason", required=True)
    p_rej.add_argument("--actor", default=None, help="current stage owner; overrides SYNC_GUARDIAN_ACTOR")
    p_fix = sub.add_parser("fix", help="微循环小修留痕，不重置阶段")
    p_fix.add_argument("--task", default=None)
    p_fix.add_argument("--reason", required=True)
    p_fix.add_argument("--no-gate", action="store_true")
    p_fix.add_argument("--actor", default=None, help="current stage owner; overrides SYNC_GUARDIAN_ACTOR")
    p_block = sub.add_parser("block", help="记录阻塞项，run 会暂停")
    p_block.add_argument("--task", default=None)
    p_block.add_argument("--kind", required=True, choices=sorted(BLOCKER_KINDS))
    p_block.add_argument("--reason", required=True)
    p_block.add_argument("--no-gate", action="store_true")
    p_block.add_argument("--actor", default=None, help="current stage owner or human; overrides SYNC_GUARDIAN_ACTOR")
    p_unblock = sub.add_parser("unblock", help="清空阻塞项")
    p_unblock.add_argument("--task", default=None)
    p_unblock.add_argument("--reason", required=True)
    p_unblock.add_argument("--no-gate", action="store_true")
    p_unblock.add_argument("--actor", default=None, help="current stage owner or human; overrides SYNC_GUARDIAN_ACTOR")
    p_run = sub.add_parser("run", help="自动流水线")
    p_run.add_argument("--task", default=None)
    p_run.add_argument("--once", action="store_true")
    p_run.add_argument("--timeout", type=int, default=3600, help="每条 agent 命令超时秒数（默认 3600）")
    args = ap.parse_args()
    if not args.cmd:
        args.cmd = "status"
        args.task = None

    root = Path(args.root).resolve()
    {"list": cmd_list, "new": cmd_new, "status": cmd_status, "next": cmd_next,
     "reject": cmd_reject, "fix": cmd_fix, "block": cmd_block,
     "unblock": cmd_unblock, "run": cmd_run}[args.cmd](root, args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff.py — 多 agent 交接驱动器（与 sync_check.py 同放 tools/）

三种触发方式：
  全自动   python tools/handoff.py run            # 从当前阶段跑到 done：每阶段调用配置的 agent 命令 → 门禁 → 推进
  半自动   python tools/handoff.py run --once     # 只跑当前一个阶段
  手动     python tools/handoff.py next --summary "设计完成"      # agent 收尾时自跑，或人手动触发
           python tools/handoff.py reject --to dev --reason "..."  # 审核打回
           python tools/handoff.py status

推进是事务式的：先写入新状态，再跑 sync_check 门禁；门禁不过则回滚并以非零码退出。
配置在 .synccheck.yml 的 handoff 段（file/stages/owners/commands）。
"""
from __future__ import annotations
import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sync_check import _load_config, _parse_front_matter, run_checks  # noqa: E402

DEFAULT_STAGES = ["design", "dev", "review", "done"]


def _die(msg: str, code: int = 1) -> None:
    print(f"[HANDOFF][FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def _today() -> str:
    return datetime.date.today().isoformat()


# ------------------------------------------------------------ state io
def _load(root: Path, config: Optional[str]) -> Tuple[Dict[str, Any], Dict[str, Any], Path, str]:
    cfg, _ = _load_config(root, config)
    ho = cfg.get("handoff") or {}
    hof = ho.get("file") if isinstance(ho, dict) else ho
    if not hof:
        _die("配置缺 handoff 段（.synccheck.yml 里配置 handoff.file 等，见技能模板）", 2)
    fp = root / hof
    if not fp.exists():
        _die(f"交接文件不存在: {fp}（从 templates/HANDOFF.md 拷一份）", 2)
    text = fp.read_text(encoding="utf-8")
    fm = _parse_front_matter(text)
    if fm is None:
        _die(f"{hof} 缺 front matter", 2)
    return cfg, (ho if isinstance(ho, dict) else {"file": ho}), fp, text


def _set_key(text: str, key: str, value: str) -> str:
    """改 front matter 中 key 的值，保留行尾注释。只改第一处（front matter 在文件头）。"""
    pat = re.compile(rf"(?m)^({re.escape(key)}:\s*)([^#\n]*?)(\s*#.*)?$")
    new, n = pat.subn(lambda m: f"{m.group(1)}{value}{m.group(3) or ''}", text, count=1)
    if n == 0:
        _die(f"交接文件缺字段 {key}")
    return new


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


def _transition(root: Path, cfg: Dict[str, Any], ho: Dict[str, Any], fp: Path, text: str,
                fm: Dict[str, Any], new_stage: str, summary: str, use_gate: bool) -> None:
    """事务式换棒：写入新状态 → 门禁 → 不过则回滚。"""
    owners = ho.get("owners") or {}
    old_stage, old_owner = fm.get("stage", "?"), fm.get("owner", "?")
    new_owner = owners.get(new_stage, old_owner)
    new_text = _set_key(text, "stage", new_stage)
    new_text = _set_key(new_text, "owner", new_owner)
    new_text = _set_key(new_text, "updated", _today())
    new_text = _append_history(
        new_text, f"| {_today()} | {old_owner} → {new_owner} | {old_stage} → {new_stage} | {summary} |")
    fp.write_text(new_text, encoding="utf-8")
    if use_gate and not _gate(root, cfg):
        fp.write_text(text, encoding="utf-8")  # 回滚
        _die(f"门禁未过，交接回滚（仍为 {old_stage}/{old_owner}）。先满足交接 DoD 再换棒。")
    print(f"[HANDOFF][OK] {old_stage}({old_owner}) → {new_stage}({new_owner})")


# ------------------------------------------------------------ commands
def cmd_status(root: Path, args) -> None:
    _, ho, fp, text = _load(root, args.config)
    fm = _parse_front_matter(text) or {}
    print(f"task : {fm.get('task')}\nstage: {fm.get('stage')}\nowner: {fm.get('owner')}\n"
          f"updated: {fm.get('updated')}")
    for d in fm.get("deliverables", []) or []:
        mark = "OK " if (root / d).exists() else "缺失"
        print(f"  deliverable [{mark}] {d}")


def cmd_next(root: Path, args) -> None:
    cfg, ho, fp, text = _load(root, args.config)
    fm = _parse_front_matter(text) or {}
    stages = ho.get("stages") or DEFAULT_STAGES
    cur = fm.get("stage")
    if cur not in stages:
        _die(f"当前 stage 非法: {cur!r}")
    if cur == stages[-1]:
        _die(f"已是最终阶段 {cur}，无可推进")
    _transition(root, cfg, ho, fp, text, fm, stages[stages.index(cur) + 1],
                args.summary or "交接", use_gate=not args.no_gate)


def cmd_reject(root: Path, args) -> None:
    cfg, ho, fp, text = _load(root, args.config)
    fm = _parse_front_matter(text) or {}
    stages = ho.get("stages") or DEFAULT_STAGES
    if args.to not in stages:
        _die(f"--to 非法: {args.to}（应为 {stages} 之一）")
    if stages.index(args.to) >= stages.index(fm.get("stage", stages[-1])):
        _die("reject 只能退回更早的阶段")
    # 打回时仓库常处于"红"状态，默认不跑门禁；退回本身要留痕
    _transition(root, cfg, ho, fp, text, fm, args.to,
                f"打回: {args.reason}", use_gate=False)
    print("[HANDOFF] 注意：问题清单请写入交接文件的\"给下一棒的说明\"。")


def cmd_run(root: Path, args) -> None:
    """自动运行：每个阶段调用配置的 agent 命令；命令成功后若 agent 未自行交接，则驱动器代为推进（含门禁）。"""
    max_steps = 12  # 防打回死循环
    for _ in range(max_steps):
        cfg, ho, fp, text = _load(root, args.config)
        fm = _parse_front_matter(text) or {}
        stages = ho.get("stages") or DEFAULT_STAGES
        cur = fm.get("stage")
        if cur == stages[-1]:
            print(f"[HANDOFF][OK] 已到最终阶段 {cur}，流水线完成。")
            return
        cmd = (ho.get("commands") or {}).get(cur)
        if not cmd:
            _die(f"阶段 {cur} 未配置 commands，无法自动运行。手动完成后跑 handoff.py next。", 2)
        print(f"[HANDOFF] 阶段 {cur}（{fm.get('owner')}）→ 调用 agent：{cmd}")
        rc = subprocess.call(cmd, shell=True, cwd=root)
        if rc != 0:
            _die(f"agent 命令退出码 {rc}，流水线中止（阶段仍为 {cur}）。")
        fm2 = _parse_front_matter(fp.read_text(encoding="utf-8")) or {}
        if fm2.get("stage") != cur:
            print(f"[HANDOFF] agent 已自行交接：{cur} → {fm2.get('stage')}")
        else:
            cfg, ho, fp, text = _load(root, args.config)  # 重读（agent 可能改了正文）
            fm = _parse_front_matter(text) or {}
            _transition(root, cfg, ho, fp, text, fm, stages[stages.index(cur) + 1],
                        f"自动交接（{cur} 阶段 agent 完成）", use_gate=True)
        if args.once:
            return
    _die(f"超过 {max_steps} 步仍未到 done（可能在反复打回），人工介入。")


def main() -> None:
    ap = argparse.ArgumentParser(description="多 agent 交接驱动器")
    ap.add_argument("--root", default=".", help="仓库根")
    ap.add_argument("--config", default=None, help=".synccheck.yml/.json 路径")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="查看当前交接状态")
    p_next = sub.add_parser("next", help="推进到下一阶段（事务式，含门禁）")
    p_next.add_argument("--summary", default=None, help="交接历史摘要")
    p_next.add_argument("--no-gate", action="store_true", help="跳过 sync_check 门禁（不建议）")
    p_rej = sub.add_parser("reject", help="审核打回到更早阶段")
    p_rej.add_argument("--to", required=True, help="退回的阶段")
    p_rej.add_argument("--reason", required=True, help="打回原因")
    p_run = sub.add_parser("run", help="自动运行：按 commands 逐阶段调 agent 并自动交接")
    p_run.add_argument("--once", action="store_true", help="只跑当前一个阶段")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    {"status": cmd_status, "next": cmd_next, "reject": cmd_reject, "run": cmd_run}[args.cmd](root, args)


if __name__ == "__main__":
    main()

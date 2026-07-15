#!/usr/bin/env python3
# Provenance: vendored from D:\repo\ashare\skills\sync-guardian\scripts\sync_check.py
# on 2026-07-12 for A42 sync-guardian hardening. This copy is now authoritative
# for the vnpy repo; divergence from the external source is expected and acceptable.
"""
sync_check.py — 文档-代码同步守卫的检查引擎（配置驱动，栈无关）

读取仓库根的 .synccheck.yml（或 .synccheck.json），校验版本单一真相与文档一致性。
不一致即以非零码退出，可直接挂 pre-commit / CI。

用法：
  python tools/sync_check.py                 # 用仓库根 .synccheck.yml
  python tools/sync_check.py --config path   # 指定配置
  python tools/sync_check.py --list          # 仅打印解析出的版本与位置，不判定

设计：只依赖标准库；version_source 支持 toml/json 点路径、plain 文件、git describe。
      YAML 配置需 pyyaml；缺失时提示改用同名 .synccheck.json（结构一致）。
      toml 解析优先 tomllib(3.11+)，否则尝试 tomli(pip install tomli)。
      含 "synccheck:ignore" 标记的行不参与版本扫描（allow_history_notes，默认开）。
      配置 handoff 后启用多 agent 交接门禁（HANDOFF.md 字段/阶段/owner/产物校验）。
"""
from __future__ import annotations
import argparse
import ast
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        if stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
        else:
            stream.reconfigure(errors="replace")


_configure_stdio()

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore  # py<3.11 fallback: pip install tomli
    except ModuleNotFoundError:
        tomllib = None

# 版本核心格式：x.y.z + 可选后缀（semver 的 -rc1/+build，或 Python 的 .post1/.dev2——
# 点后缀段须含字母，避免把 IP 第四段当后缀）。_VER_RE 与 _extract_symbol_version 共用，保证两边解析一致。
_VER_CORE = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*|(?:\.[0-9A-Za-z]*[A-Za-z][0-9A-Za-z]*)+)?"
# 带边界匹配：不吃 IP(192.168.1.1)、不截断更长版本(11.2.34)、允许句尾标点
_VER_RE = re.compile(rf"(?<![\d.])v?({_VER_CORE})(?!\.?\d)")

IGNORE_MARK = "synccheck:ignore"  # 行含此标记则不参与版本扫描（allow_history_notes，默认开）
HANDOFF_DEFAULT_STAGES = ["design", "dev", "review", "done"]


def _fail(msg: str) -> None:
    print(f"[SYNC-CHECK][FAIL] {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"[SYNC-CHECK][OK] {msg}")


# ---------------------------------------------------------------- config
def _load_config(root: Path, explicit: str | None) -> tuple[dict[str, Any], Path]:
    cands = [Path(explicit)] if explicit else [root / ".synccheck.yml",
                                               root / ".synccheck.yaml",
                                               root / ".synccheck.json"]
    for p in cands:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if p.suffix == ".json":
                return json.loads(text), p
            try:
                import yaml  # type: ignore
            except Exception:  # noqa: BLE001
                print("[SYNC-CHECK] 需要 pyyaml 解析 YAML；或改用同名 .synccheck.json（结构一致）。",
                      file=sys.stderr)
                sys.exit(2)
            return yaml.safe_load(text), p
    print(f"[SYNC-CHECK] 未找到配置（尝试过：{[str(c) for c in cands]}）", file=sys.stderr)
    sys.exit(2)


# ------------------------------------------------------------ version src
def _dig(data: Any, dotpath: str) -> Any:
    cur = data
    for key in dotpath.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _extract_symbol_version(text: str, symbol: str) -> str | None:
    """从 `symbol = "x.y.z"` / `symbol: "x.y.z"` 抽取版本。"""
    m = re.search(rf"{re.escape(symbol)}\s*[:=]\s*['\"]?v?({_VER_CORE})['\"]?", text)
    return m.group(1) if m else None


def _resolve_version_source(root: Path, spec: str) -> str:
    """spec: 'file::dotpath' | 'VERSION::' | 'git::describe'"""
    if spec.startswith("git::"):
        try:
            out = subprocess.check_output(["git", "describe", "--tags", "--always"],
                                          cwd=root, text=True).strip()
        except Exception as e:  # noqa: BLE001
            _fail(f"git describe 失败: {e}")
            sys.exit(1)
        m = _VER_RE.search(out)
        if not m:
            _fail(f"git describe 结果无版本号: {out!r}")
            sys.exit(1)
        return m.group(1)

    if "::" not in spec:
        _fail(f"version_source 格式非法（应含 '::'）: {spec}")
        sys.exit(1)
    fname, dotpath = spec.split("::", 1)
    fp = root / fname
    if not fp.exists():
        _fail(f"version_source 文件不存在: {fp}")
        sys.exit(1)
    raw = fp.read_text(encoding="utf-8")

    if fname.endswith(".toml"):
        if tomllib is None:
            _fail("需 Python 3.11+ 的 tomllib 解析 toml version_source")
            sys.exit(1)
        val = _dig(tomllib.loads(raw), dotpath)
    elif fname.endswith(".json"):
        val = _dig(json.loads(raw), dotpath)
    elif dotpath == "":  # plain VERSION file
        val = raw.strip()
    else:  # file::symbol
        val = _extract_symbol_version(raw, dotpath)

    if not val:
        _fail(f"version_source 解析不出版本: {spec}")
        sys.exit(1)
    m = _VER_RE.search(str(val))
    if not m:
        _fail(f"version_source 值非法版本: {val!r}")
        sys.exit(1)
    return m.group(1)


# ------------------------------------------------------------ must_match
def _versions_in(root: Path, entry: str, allow_ignore: bool = True) -> tuple[list[str], str | None]:
    """返回 (该位置出现的版本列表, 错误说明或None)。entry: 'file' 或 'file::symbol'"""
    if "::" in entry:
        fname, symbol = entry.split("::", 1)
        fp = root / fname
        if not fp.exists():
            return [], f"文件不存在: {fp}"
        v = _extract_symbol_version(fp.read_text(encoding="utf-8"), symbol)
        return ([v] if v else []), (None if v else f"符号 {symbol} 未找到版本")
    fp = root / entry
    if not fp.exists():
        return [], f"文件不存在: {fp}"
    text = fp.read_text(encoding="utf-8")
    if allow_ignore:  # 含标记的行豁免（沿革注释、依赖版本等合法旧版本提及）
        text = "\n".join(line for line in text.splitlines() if IGNORE_MARK not in line)
    vers = _VER_RE.findall(text)
    return vers, None


# ------------------------------------------------------------- handoff
def _parse_front_matter(text: str) -> dict[str, Any] | None:
    """解析 markdown 头部 --- 包裹的 front matter（仅扁平 key: value 与字符串列表，够用且零依赖）。
    未闭合或不存在返回 None。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: dict[str, Any] = {}
    cur_list: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        raw = re.sub(r"\s+#.*$", "", line).rstrip()  # 去行尾注释
        if not raw.strip():
            continue
        if raw.lstrip().startswith("- ") and cur_list is not None:
            fm[cur_list].append(raw.lstrip()[2:].strip().strip("'\""))
        elif ":" in raw:
            k, v = raw.split(":", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if v == "[]":
                fm[k], cur_list = [], None
            elif v == "":
                fm[k], cur_list = [], k  # 块列表开头
            else:
                fm[k], cur_list = v, None
    return None  # front matter 未闭合


def _resolve_repo_relative(root: Path, base: Path, value: Any) -> tuple[Path | None, str | None]:
    """Resolve a committed path only when it stays inside the repository."""
    raw = str(value or "").strip()
    if not raw:
        return None, "空路径"
    p = Path(raw)
    if p.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith(("\\\\", "//")):
        return None, "绝对路径不允许"
    repo = root.resolve()
    target = (base / raw).resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        return None, "路径越界"
    return target, None


def handoff_task_stages(ho: dict[str, Any], fm: dict[str, Any]) -> list[str]:
    base = ho.get("stages") or HANDOFF_DEFAULT_STAGES
    track = str(fm.get("track", "full"))
    tracks = ho.get("tracks") if isinstance(ho, dict) else None
    if isinstance(tracks, dict):
        if track in tracks:
            return list(tracks[track])
        return []
    if track == "fast" and len(base) > 2:
        return list(base[1:])
    return list(base)


def handoff_missing_stage_owners(ho: dict[str, Any], stages: list[str]) -> list[str]:
    """Configured tracks must keep actor ownership explicit for every active stage."""
    if not isinstance(ho, dict) or not isinstance(ho.get("tracks"), dict):
        return []
    owners = ho.get("owners") or {}
    return [stage for stage in stages if stage != "done" and stage not in owners]


DEFAULT_REJECT_FROM = {  # 打回白名单：from_stage → 允许退回的阶段（handoff.reject_from 可覆盖）
    "review": ["dev", "design"],
    "dev": ["design"],
    "plan-review": ["design"],
}


def handoff_reject_from(ho: Any) -> dict[str, list[str]]:
    """打回白名单的唯一定义：sync_check 门禁与 handoff.py 驱动器共用。"""
    if isinstance(ho, dict) and isinstance(ho.get("reject_from"), dict):
        return {str(k): list(v or []) for k, v in ho["reject_from"].items()}
    return DEFAULT_REJECT_FROM


def _clean_transition_part(value: Any) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\(.*?\)", "", value)
    return value.strip()


def _transition_evidence(fm: dict[str, Any]) -> dict[str, str] | None:
    """只读驱动器原子写入的 last_transition_* 字段，不从交接历史表反推——
    历史行可能产生于旧的 stages 配置，用当前配置校验历史会在配置迁移时误报。"""
    keys = {
        "actor": "last_transition_actor",
        "from_stage": "last_transition_from_stage",
        "to_stage": "last_transition_to_stage",
        "from_owner": "last_transition_from_owner",
        "to_owner": "last_transition_to_owner",
    }
    if not all(fm.get(k) for k in keys.values()):
        return None
    ev = {name: _clean_transition_part(fm[src]) for name, src in keys.items()}
    ev["kind"] = _clean_transition_part(fm.get("last_transition_kind", "")) or ""
    return ev


def _check_transition_policy(ho: Any, fm: dict[str, Any], label: str, errors: list[str]) -> None:
    """按交接类型分流校验：next（前进）必须 +1 步且 actor 为该阶段 owner；
    reject（打回）必须命中白名单；fix（微循环）不变更阶段，仅查 actor。"""
    if not isinstance(ho, dict):
        return
    ev = _transition_evidence(fm)
    if not ev:
        return

    stages = handoff_task_stages(ho, fm)
    owners = ho.get("owners") or {}
    actor, from_stage, to_stage = ev["actor"], ev["from_stage"], ev["to_stage"]
    kind = ev["kind"]
    if not kind and from_stage in stages and to_stage in stages:
        # 旧版驱动器写入的记录无 kind：按方向推断，保持存量文件兼容
        kind = "reject" if stages.index(to_stage) < stages.index(from_stage) else "next"

    expected_actor = owners.get(from_stage)
    if expected_actor and actor != expected_actor:
        errors.append(
            f"handoff[{label}]: illegal transition actor {actor!r}; "
            f"stage {from_stage!r} requires {expected_actor!r}"
        )

    if kind == "fix":
        return

    if kind == "reject":
        allowed = handoff_reject_from(ho).get(from_stage, [])
        if to_stage not in allowed:
            errors.append(
                f"handoff[{label}]: illegal reject {from_stage}->{to_stage}; "
                f"allowed targets: {allowed}"
            )
        return

    if from_stage in stages and to_stage in stages \
            and stages.index(to_stage) - stages.index(from_stage) != 1:
        errors.append(
            f"handoff[{label}]: illegal transition {from_stage}->{to_stage}; "
            "forward handoff must advance one stage at a time"
        )


def _check_deliverables_are_tracked_and_fresh(
    root: Path, cfg: dict[str, Any], fp: Path, label: str, errors: list[str]
) -> None:
    """Dev->review 阶段要求至少一个 deliverable 在当前 design->dev 之后被 git 跟踪/更新过。
    若 deliverable 位于 git-ignored 目录下，还要求它出现在 dev-stage commit 的 show --stat 中
    （即被 git add -f 强制加入版本控制），而不是仅存在于磁盘上。"""
    policy = cfg.get("deliverables_policy") if isinstance(cfg, dict) else None
    if not (policy or {}).get("require_new_evidence_on_dev_to_review"):
        return
    text = fp.read_text(encoding="utf-8")
    fm = _parse_front_matter(text)
    if not fm:
        return
    stage = fm.get("stage")
    ev = _transition_evidence(fm)
    if stage != "review":
        return
    if not ev or ev.get("from_stage") != "dev" or ev.get("to_stage") != "review":
        return
    deliverables = fm.get("deliverables") or []
    if not deliverables:
        errors.append(f"handoff[{label}]: stage=review 缺少 deliverables，无法验证 dev 阶段产出")
        return

    # 找到 design->dev 转换 commit：扫描 HANDOFF.md 的 git 历史，定位实际把
    # `stage:` 从 design 改为 dev 的那个 commit（比单纯按时间或 commit message 更稳健，
    # 可免疫中间 fix 微循环提交）。
    design_to_dev_commit: str | None = None
    try:
        out = subprocess.check_output(
            ["git", "log", "--format=%H", "--follow", "--", fp.relative_to(root).as_posix()],
            cwd=root, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        out = ""
    candidate_commits = [c for c in out.splitlines() if c]
    for commit in candidate_commits:
        try:
            diff = subprocess.check_output(
                ["git", "show", commit, "--", fp.relative_to(root).as_posix()],
                cwd=root, text=True, stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            continue
        # diff 中同时出现 design 行的删除和 dev 行的新增（允许前后有 owner/updated 等变更）
        has_design_removed = re.search(r"^-(?:\s*stage:\s*)design\b", diff, re.M) is not None
        has_dev_added = re.search(r"^\+(?:\s*stage:\s*)dev\b", diff, re.M) is not None
        if has_design_removed and has_dev_added:
            design_to_dev_commit = commit
            break
    if not design_to_dev_commit and len(candidate_commits) >= 2:
        # 稳健 fallback：跳过最近一次（dev->review）提交，取上一次作为 design->dev
        design_to_dev_commit = candidate_commits[1]
    if not design_to_dev_commit and candidate_commits:
        design_to_dev_commit = candidate_commits[0]
    if not design_to_dev_commit:
        errors.append(f"handoff[{label}]: 无法定位 design->dev 转换 commit，无法验证 deliverables 新鲜度")
        return

    # 检查每个 deliverable：是否被任何晚于 design_to_dev_commit 的 commit 触碰过
    freshly_tracked: list[str] = []
    stale_deliverables: list[str] = []
    ignored_untracked: list[str] = []
    for rel in deliverables:
        target, path_err = _resolve_repo_relative(root, root, rel)
        if path_err:
            stale_deliverables.append(f"{rel} ({path_err})")
            continue
        if target is None or not target.exists():
            stale_deliverables.append(f"{rel} (不存在)")
            continue
        # 1. 是否被任何 commit 跟踪过
        try:
            latest_commit = subprocess.check_output(
                ["git", "log", "--follow", "-1", "--format=%H", "--", rel],
                cwd=root, text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:  # noqa: BLE001
            latest_commit = ""
        if not latest_commit:
            stale_deliverables.append(f"{rel} (从未被 git 跟踪)")
            continue
        # 2. 是否在 design->dev 之后被更新
        try:
            is_ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", design_to_dev_commit, latest_commit],
                cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode == 0
        except Exception:  # noqa: BLE001
            is_ancestor = False
        if not is_ancestor:
            stale_deliverables.append(f"{rel} (自 design->dev 转换后未被更新)")
            continue
        # 3. 若位于 git-ignored 目录，需确认出现在 design->dev 之后的某个 commit 的 show --stat 中
        try:
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", rel],
                cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode == 0
        except Exception:  # noqa: BLE001
            ignored = False
        if ignored:
            try:
                range_log = subprocess.check_output(
                    ["git", "log", f"{design_to_dev_commit}..{latest_commit}", "--format=%H", "--", rel],
                    cwd=root, text=True, stderr=subprocess.DEVNULL,
                ).strip()
            except Exception:  # noqa: BLE001
                range_log = ""
            in_show_stat = False
            for commit in range_log.splitlines():
                if not commit:
                    continue
                try:
                    show_stat = subprocess.check_output(
                        ["git", "show", "--stat", "--format=", commit],
                        cwd=root, text=True, stderr=subprocess.DEVNULL,
                    )
                except Exception:  # noqa: BLE001
                    continue
                # 提取 stat 行中的文件名部分（支持含空格路径较困难，这里做近似匹配）
                if rel in show_stat or target.name in show_stat:
                    in_show_stat = True
                    break
            if not in_show_stat:
                ignored_untracked.append(f"{rel} (位于 git-ignored 目录但未在 dev-stage commit 中 git add -f)")
                continue
        freshly_tracked.append(rel)

    if ignored_untracked:
        errors.append(f"handoff[{label}]: deliverable 未强制加入版本控制: {', '.join(ignored_untracked)}")
    if not freshly_tracked and not ignored_untracked:
        # 没有任何 deliverable 在 design->dev 之后被新鲜跟踪：dev 阶段没有可审计的产出
        details = "; ".join(stale_deliverables) if stale_deliverables else "无 deliverable"
        errors.append(f"handoff[{label}]: 没有 deliverable 在 design->dev 之后被新鲜跟踪 ({details})")


def _check_handoff_file(root: Path, ho: Any, fp: Path, label: str, errors: list[str]) -> None:
    """校验单个交接文件：字段完整、stage 合法、owner 与阶段匹配、deliverables 可达。"""
    if not fp.exists():
        errors.append(f"handoff: 文件不存在 {fp}")
        return
    text = fp.read_text(encoding="utf-8")
    fm = _parse_front_matter(text)
    if fm is None:
        errors.append(f"handoff[{label}]: 缺 front matter（文件须以 --- 包裹的 key: value 头开始）")
        return
    for key in ("task", "stage", "owner", "updated"):
        if not fm.get(key):
            errors.append(f"handoff[{label}]: 缺必需字段 {key}")
    stages = handoff_task_stages(ho, fm) if isinstance(ho, dict) else HANDOFF_DEFAULT_STAGES
    if isinstance(ho, dict) and isinstance(ho.get("tracks"), dict) and not stages:
        errors.append(f"handoff[{label}]: track 非法 {fm.get('track', 'full')!r}（应为 {list(ho['tracks'])} 之一）")
    missing_owners = handoff_missing_stage_owners(ho, stages) if isinstance(ho, dict) else []
    if missing_owners:
        errors.append(f"handoff[{label}]: configured track owner 缺失: {missing_owners}")
    stage = fm.get("stage")
    if stage and stage not in stages:
        errors.append(f"handoff[{label}]: stage 非法 {stage!r}（应为 {stages} 之一）")
    owners = ho.get("owners") if isinstance(ho, dict) else None
    if owners and stage in owners and fm.get("owner") and fm["owner"] != owners[stage]:
        errors.append(f"handoff[{label}]: stage={stage} 的接棒者应为 {owners[stage]}，"
                      f"实际 {fm['owner']}（推进了阶段忘改 owner？）")
    for rel in fm.get("deliverables", []) or []:
        target, path_err = _resolve_repo_relative(root, root, rel)
        if path_err:
            errors.append(f"handoff[{label}]: deliverable 路径非法 {rel}: {path_err}")
        elif target is not None and not target.exists():
            errors.append(f"handoff[{label}]: deliverable 不存在 {rel}")

    _check_transition_policy(ho, fm, label, errors)


def _check_handoff(root: Path, cfg: dict[str, Any], errors: list[str]) -> None:
    """多 agent 交接门禁。两种模式：
    dir（多任务并行）：handoffs/ 下每个 *.md 是一个任务的交接文件，逐一校验；
    file（单任务）：仓库根单一 HANDOFF.md。"""
    ho = cfg.get("handoff") or {}
    if isinstance(ho, dict) and ho.get("dir"):
        d = root / ho["dir"]
        if not d.exists():
            errors.append(f"handoff: 任务目录不存在 {d}")
            return
        for fp in sorted(d.glob("*.md")):
            _check_handoff_file(root, ho, fp, f"{ho['dir'].rstrip('/')}/{fp.name}", errors)
        return
    hof = ho.get("file") if isinstance(ho, dict) else ho
    if hof:
        fp = root / hof
        _check_handoff_file(root, ho, fp, str(hof), errors)
        _check_deliverables_are_tracked_and_fresh(root, cfg, fp, str(hof), errors)


# ------------------------------------------------------------- checks
def run_checks(root: Path, cfg: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allow_ignore = cfg.get("allow_history_notes", True)
    truth = _resolve_version_source(root, cfg["version_source"])
    _ok(f"版本单一真相 = {truth}  (source: {cfg['version_source']})")

    # 1. must_match
    for entry in cfg.get("must_match", []) or []:
        vers, err = _versions_in(root, entry, allow_ignore)
        if err:
            errors.append(f"must_match[{entry}]: {err}")
            continue
        bad = [v for v in vers if v != truth]
        if not vers:
            errors.append(f"must_match[{entry}]: 未发现任何版本号")
        elif bad:
            errors.append(f"must_match[{entry}]: 出现与真相不符的版本 {sorted(set(bad))}（应为 {truth}）")

    # 2. changelog（带边界匹配：1.2.3 不会被 11.2.34 或 "from 1.2.30" 误满足）
    cl = cfg.get("changelog") or {}
    clf = cl.get("file") if isinstance(cl, dict) else cl
    if clf:
        fp = root / clf
        if not fp.exists():
            errors.append(f"changelog: 文件不存在 {fp}")
        elif not re.search(rf"(?<![\d.]){re.escape(truth)}(?!\.?\d)",
                           fp.read_text(encoding="utf-8")):
            errors.append(f"changelog[{clf}]: 缺当前版本 {truth} 的条目")

    # 3. doc_index existence（支持带 #锚点 的内联链接与引用式链接 [x]: docs/a.md）
    idx = cfg.get("doc_index")
    if idx:
        fp = root / idx
        if not fp.exists():
            errors.append(f"doc_index: 文件不存在 {fp}")
        else:
            text = fp.read_text(encoding="utf-8")
            rels = re.findall(r"\(([^)\s#]+\.md)(?:#[^)]*)?\)", text)
            rels += re.findall(r"^\[[^\]]+\]:\s*(\S+\.md)", text, re.M)
            for rel in rels:
                if rel.startswith(("http://", "https://")):
                    continue
                candidates = []
                path_errors = []
                for base in (fp.parent, root):
                    target, path_err = _resolve_repo_relative(root, base, rel)
                    if path_err:
                        path_errors.append(path_err)
                    elif target is not None:
                        candidates.append(target)
                if candidates and any(target.exists() for target in candidates):
                    continue
                if path_errors and not candidates:
                    errors.append(f"doc_index: 路径非法 {rel}: {path_errors[0]}")
                else:
                    errors.append(f"doc_index: 引用了不存在的文档 {rel}")

    # 4. archive-not-in-root
    for pat in cfg.get("archive_must_not_be_in_root", []) or []:
        for hit in root.glob(pat):
            errors.append(f"历史文档回流（应在归档区）: {hit.relative_to(root)}")

    # 5. handoff（多 agent 交接门禁，配置了才检查）
    if cfg.get("handoff"):
        _check_handoff(root, cfg, errors)

    # 6. project-level VERSION/CHANGELOG freshness (A60)
    _check_project_version_freshness(root, cfg, errors)

    # 7. diagnostics banner check (A54)
    _check_diagnostics_banner(root, cfg, errors)

    # 8. archive_dir 存在性（仅提示，不阻塞）
    ad = cfg.get("archive_dir")
    if ad and not (root / ad).exists():
        print(f"[SYNC-CHECK][WARN] archive_dir 不存在: {ad}（仅提示，不 FAIL）")

    return errors


def _is_path_exempt(path: Path, root: Path, skip_patterns: set[str],
                      exempt_dirs: list[str]) -> bool:
    """Return True if a diagnostics path matches a skip pattern or sits in an exempt dir."""
    if any(fnmatch.fnmatch(path.name, pat) for pat in skip_patterns):
        return True
    for rel in exempt_dirs:
        exempt_path = (root / rel).resolve()
        try:
            path.relative_to(exempt_path)
            return True
        except ValueError:
            pass
    return False


def _check_diagnostics_banner(root: Path, cfg: dict[str, Any], errors: list[str]) -> None:
    """A54 gate: every diagnostics/*.md report must carry the RESEARCH-ONLY banner.

    Configured under ``diagnostics_banner_check``:
      dirs: [examples/czsc_strategy/diagnostics]
      banner: "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->"
      skip: [WORK_LOG.md, ACCEPTANCE.md, audit_issue_diagnostics_*.md, ...]
      exempt_dirs: [examples/czsc_strategy/diagnostics/archive]
    """
    check = cfg.get("diagnostics_banner_check")
    if not isinstance(check, dict):
        return

    banner = check.get("banner")
    if not banner:
        return

    dirs = check.get("dirs") or []
    if check.get("dir"):
        dirs = [check["dir"]]
    if not dirs:
        return

    skip_patterns: set[str] = set(check.get("skip") or [])
    exempt_dirs: list[str] = list(check.get("exempt_dirs") or [])

    for rel in dirs:
        d = root / rel
        if not d.exists():
            errors.append(f"diagnostics_banner_check: directory not found {rel}")
            continue
        for path in sorted(d.rglob("*.md")):
            if _is_path_exempt(path, root, skip_patterns, exempt_dirs):
                continue
            text = path.read_text(encoding="utf-8")
            if banner not in text:
                rel_path = path.relative_to(root).as_posix()
                errors.append(
                    f"diagnostics_banner_check: {rel_path} lacks RESEARCH-ONLY banner"
                )


def _repo_relative(root: Path, target: Path) -> str:
    """Return a POSIX path string for ``target`` relative to ``root``."""
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return target.as_posix()


_SAFE_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


def _safe_eval_node(node: ast.AST) -> Any:
    """Evaluate a literal-ish AST node, tolerating simple numeric arithmetic.

    ``ast.literal_eval`` only accepts pure literals and raises on any expression
    node -- but real config dicts commonly write derived numeric constants as
    small arithmetic expressions (e.g. ``3600 * 24`` for "one day in seconds").
    This extends literal evaluation with numeric ``BinOp``/``UnaryOp`` support
    (Add/Sub/Mult/Div on constants only) while still rejecting anything that
    could have side effects (calls, names, comprehensions, etc.).
    """
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return _SAFE_BINOPS[type(node.op)](left, right)
        raise ValueError("non-numeric operand in config arithmetic expression")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_safe_eval_node(node.operand)
    if isinstance(node, ast.Dict):
        return {
            _safe_eval_node(k): _safe_eval_node(v)
            for k, v in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_safe_eval_node(elt) for elt in node.elts]
    return ast.literal_eval(node)


def _config_surface_fingerprint(text: str, watch_names: list[str]) -> dict[str, str]:
    """Parse a Python file and return a JSON-normalised fingerprint for watched dicts.

    Only top-level assignments whose names are in ``watch_names`` are considered.
    The value must be a dict literal, evaluated via ``_safe_eval_node`` (a
    literal-eval superset that also tolerates simple numeric arithmetic like
    ``3600 * 24``).  The fingerprint captures key additions/removals and value
    changes, but ignores comments or formatting-only edits.
    """
    tree = ast.parse(text)
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in watch_names:
                    value = _safe_eval_node(node.value)
                    if not isinstance(value, dict):
                        raise ValueError(f"{target.id} is not a dict literal")
                    result[target.id] = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return result


def _find_gate_since_commit(root: Path, cfg_path: Path) -> str | None:
    """Locate the commit that introduced ``project_version_freshness`` into config.

    This dynamic cutoff makes the gate apply only to commits after it landed,
    avoiding retroactive failures for changes that shipped before the check existed.
    """
    rel = _repo_relative(root, cfg_path)
    try:
        out = subprocess.check_output(
            ["git", "log", "--reverse", "--format=%H", "-S", "project_version_freshness", "--", rel],
            cwd=root, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return None
    lines = [line for line in out.splitlines() if line]
    return lines[0] if lines else None


def _commits_after(root: Path, since: str) -> list[str]:
    """Return commits strictly after ``since`` up to HEAD, oldest first."""
    try:
        out = subprocess.check_output(
            ["git", "log", "--reverse", "--format=%H", f"{since}..HEAD"],
            cwd=root, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return []
    return [line for line in out.splitlines() if line]


def _files_changed_in_commit(root: Path, commit: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            cwd=root, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return []
    return [line for line in out.splitlines() if line]


def _file_at_commit(root: Path, commit: str, rel_path: str) -> str | None:
    # NOTE: explicit encoding="utf-8" is required here -- on Windows, subprocess's
    # default text-mode decoding uses the system locale (often GBK/cp936), which
    # raises UnicodeDecodeError on any UTF-8 source file containing non-ASCII
    # characters (e.g. Chinese comments in config.py). That exception was
    # previously swallowed by the broad except below, silently turning a decode
    # failure into a false "could not read" gate failure (found by A67's review).
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{rel_path}"],
            cwd=root, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        return None


def _first_parent(root: Path, commit: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", f"{commit}^"],
            cwd=root, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL,
        ).strip() or None
    except Exception:  # noqa: BLE001
        return None


def _check_project_version_freshness(root: Path, cfg: dict[str, Any], errors: list[str]) -> None:
    """A60 gate: project VERSION/CHANGELOG must move when config surface changes.

    Whenever a commit touches a watched top-level dict in the project's config file,
    the same commit must also touch the project's VERSION file or CHANGELOG file.
    The gate only looks at commits after the ``project_version_freshness`` block
    itself was introduced, so it never retroactively punishes older changes.
    """
    pvf = cfg.get("project_version_freshness")
    if not isinstance(pvf, dict):
        return

    project_root_rel = str(pvf.get("project_root", ".")).strip()
    project_root = (root / project_root_rel).resolve()
    config_file_rel = str(pvf.get("config_file", "config.py"))
    version_file_rel = str(pvf.get("version_file", "VERSION"))
    changelog_file_rel = str(pvf.get("changelog_file", "CHANGELOG.md"))
    watch_variables = list(pvf.get("watch_variables", ["STRATEGY_CONFIG", "BACKTEST_CONFIG"]) or [])

    config_path = project_root / config_file_rel
    version_path = project_root / version_file_rel
    changelog_path = project_root / changelog_file_rel
    label = project_root_rel

    for p, name in ((config_path, config_file_rel), (version_path, version_file_rel),
                    (changelog_path, changelog_file_rel)):
        if not p.exists():
            errors.append(f"project_version_freshness[{label}]: {name} not found")
            return

    # Use the loaded config file to find the gate-introduction commit.
    cfg_path = root / ".synccheck.yml"
    if not cfg_path.exists():
        cfg_path = root / ".synccheck.yaml"
    if not cfg_path.exists():
        cfg_path = root / ".synccheck.json"
    since = _find_gate_since_commit(root, cfg_path) if cfg_path.exists() else None
    if not since:
        # Gate has not been committed yet; skip silently until it lands.
        return

    config_rel = _repo_relative(root, config_path)
    version_rel = _repo_relative(root, version_path)
    changelog_rel = _repo_relative(root, changelog_path)

    for commit in _commits_after(root, since):
        changed = _files_changed_in_commit(root, commit)
        if config_rel not in changed:
            continue

        parent = _first_parent(root, commit)
        before_text = _file_at_commit(root, parent, config_rel) if parent else ""
        after_text = _file_at_commit(root, commit, config_rel)
        if before_text is None or after_text is None:
            errors.append(
                f"project_version_freshness[{label}]: commit {commit[:8]} "
                f"could not read {config_file_rel}"
            )
            continue

        try:
            before_fp = _config_surface_fingerprint(before_text, watch_variables) if before_text else {}
        except Exception as e:  # noqa: BLE001
            errors.append(
                f"project_version_freshness[{label}]: commit {commit[:8]} "
                f"parent {config_file_rel} parse error: {e}"
            )
            continue
        try:
            after_fp = _config_surface_fingerprint(after_text, watch_variables)
        except Exception as e:  # noqa: BLE001
            errors.append(
                f"project_version_freshness[{label}]: commit {commit[:8]} "
                f"{config_file_rel} parse error: {e}"
            )
            continue

        changed_vars = [v for v in watch_variables if before_fp.get(v) != after_fp.get(v)]
        if not changed_vars:
            continue

        if version_rel not in changed and changelog_rel not in changed:
            errors.append(
                f"project_version_freshness[{label}]: commit {commit[:8]} changed "
                f"{', '.join(changed_vars)} top-level keys in {config_file_rel} "
                f"but touched neither {version_file_rel} nor {changelog_file_rel}"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="文档-代码同步守卫检查引擎")
    ap.add_argument("--config", default=None, help=".synccheck.yml/.json 路径")
    ap.add_argument("--root", default=".", help="仓库根，默认当前目录")
    ap.add_argument("--list", action="store_true", help="仅解析版本，不判定")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg, cfg_path = _load_config(root, args.config)
    print(f"[SYNC-CHECK] 配置: {cfg_path}")

    if not isinstance(cfg, dict) or not cfg.get("version_source"):
        _fail("配置缺少 version_source（唯一真相），无法检查。")
        sys.exit(2)

    if args.list:
        print(f"版本真相: {_resolve_version_source(root, cfg['version_source'])}")
        for entry in cfg.get("must_match", []) or []:
            vers, err = _versions_in(root, entry, cfg.get("allow_history_notes", True))
            print(f"  {entry}: {err or sorted(set(vers))}")
        return

    errors = run_checks(root, cfg)
    if errors:
        for e in errors:
            _fail(e)
        # 输出用纯 ASCII 标记，避免 Windows GBK 管道/CI 重定向下 emoji 触发 UnicodeEncodeError
        print(f"\n[SYNC-CHECK] FAIL: {len(errors)} 项不一致，提交/CI 应拦截。", file=sys.stderr)
        sys.exit(1)
    print("\n[SYNC-CHECK] PASS: 版本与文档一致。")


if __name__ == "__main__":
    main()

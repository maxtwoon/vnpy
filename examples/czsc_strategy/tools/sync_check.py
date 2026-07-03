#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
      含 "synccheck:ignore" 标记的行不参与版本扫描（allow_history_notes 控制，默认开）。
      配置 handoff 后启用多 agent 交接门禁（HANDOFF.md 字段/阶段/owner/产物校验）。
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _fail(msg: str) -> None:
    print(f"[SYNC-CHECK][FAIL] {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"[SYNC-CHECK][OK] {msg}")


# ---------------------------------------------------------------- config
def _load_config(root: Path, explicit: Optional[str]) -> Tuple[Dict[str, Any], Path]:
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


def _extract_symbol_version(text: str, symbol: str) -> Optional[str]:
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
def _versions_in(root: Path, entry: str, allow_ignore: bool = True) -> Tuple[List[str], Optional[str]]:
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
        text = "\n".join(l for l in text.splitlines() if IGNORE_MARK not in l)
    vers = _VER_RE.findall(text)
    return vers, None


# ------------------------------------------------------------- handoff
def _parse_front_matter(text: str) -> Optional[Dict[str, Any]]:
    """解析 markdown 头部 --- 包裹的 front matter（仅扁平 key: value 与字符串列表，够用且零依赖）。
    未闭合或不存在返回 None。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: Dict[str, Any] = {}
    cur_list: Optional[str] = None
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


def _check_handoff(root: Path, ho: Any, errors: List[str]) -> None:
    """多 agent 交接门禁：字段完整、stage 合法、owner 与阶段匹配、deliverables 可达。"""
    hof = ho.get("file") if isinstance(ho, dict) else ho
    if not hof:
        return
    fp = root / hof
    if not fp.exists():
        errors.append(f"handoff: 文件不存在 {fp}")
        return
    fm = _parse_front_matter(fp.read_text(encoding="utf-8"))
    if fm is None:
        errors.append(f"handoff[{hof}]: 缺 front matter（文件须以 --- 包裹的 key: value 头开始）")
        return
    for key in ("task", "stage", "owner", "updated"):
        if not fm.get(key):
            errors.append(f"handoff[{hof}]: 缺必需字段 {key}")
    stages = (ho.get("stages") if isinstance(ho, dict) else None) or ["design", "dev", "review", "done"]
    stage = fm.get("stage")
    if stage and stage not in stages:
        errors.append(f"handoff[{hof}]: stage 非法 {stage!r}（应为 {stages} 之一）")
    owners = ho.get("owners") if isinstance(ho, dict) else None
    if owners and stage in owners and fm.get("owner") and fm["owner"] != owners[stage]:
        errors.append(f"handoff[{hof}]: stage={stage} 的接棒者应为 {owners[stage]}，"
                      f"实际 {fm['owner']}（推进了阶段忘改 owner？）")
    for rel in fm.get("deliverables", []) or []:
        if not (root / rel).exists():
            errors.append(f"handoff[{hof}]: deliverable 不存在 {rel}")


# ------------------------------------------------------------- checks
def run_checks(root: Path, cfg: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
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
                target = (fp.parent / rel).resolve()
                if not target.exists() and not (root / rel).exists():
                    errors.append(f"doc_index: 引用了不存在的文档 {rel}")

    # 4. archive-not-in-root
    for pat in cfg.get("archive_must_not_be_in_root", []) or []:
        for hit in root.glob(pat):
            errors.append(f"历史文档回流（应在归档区）: {hit.relative_to(root)}")

    # 5. handoff（多 agent 交接门禁，配置了才检查）
    if cfg.get("handoff"):
        _check_handoff(root, cfg["handoff"], errors)

    # 6. archive_dir 存在性（仅提示，不阻塞）
    ad = cfg.get("archive_dir")
    if ad and not (root / ad).exists():
        print(f"[SYNC-CHECK][WARN] archive_dir 不存在: {ad}（仅提示，不 FAIL）")

    return errors


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

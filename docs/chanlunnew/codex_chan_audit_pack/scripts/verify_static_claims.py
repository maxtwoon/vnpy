#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态复核脚本：不依赖 czsc。

用途：验证 ChatGPT 审计中可以通过源码/包结构判断的断言。
运行：python scripts/verify_static_claims.py
"""
from __future__ import annotations
import ast
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "payload" / "chan_system_v1.0.2_extracted"
SRC = PKG / "src"
TESTS = PKG / "tests"
README = PKG / "README.md"
DOCS = PKG / "docs"
ORIGINAL_ZIP = ROOT / "payload" / "files_2_original.zip"

RESULTS = []

def add(code: str, ok: bool, evidence: str, severity: str = "info"):
    RESULTS.append({"claim": code, "ok": bool(ok), "severity": severity, "evidence": evidence})

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def compile_file(p: Path) -> bool:
    try:
        ast.parse(read(p), filename=str(p))
        return True
    except SyntaxError as e:
        add("B1", False, f"{p}: SyntaxError {e}", "high")
        return False

# B1: syntax compile
for name in ["czsc_adapter.py", "bsp_state_machine.py", "xd_segment.py"]:
    p = SRC / name
    if p.exists():
        ok = compile_file(p)
        add("B1", ok, f"{name} AST parse {'OK' if ok else 'FAILED'}", "high" if not ok else "info")
    else:
        add("B1", False, f"missing {p}", "high")

adapter = read(SRC / "czsc_adapter.py") if (SRC / "czsc_adapter.py").exists() else ""
state = read(SRC / "bsp_state_machine.py") if (SRC / "bsp_state_machine.py").exists() else ""
xd = read(SRC / "xd_segment.py") if (SRC / "xd_segment.py").exists() else ""
test_basic = read(TESTS / "test_basic.py") if (TESTS / "test_basic.py").exists() else ""
readme = read(README) if README.exists() else ""

# C1: xd / xd_zs fixed empty in adapter output
c1 = bool(re.search(r'"xd"\s*:\s*\[\s*\]', adapter)) and bool(re.search(r'"xd_zs"\s*:\s*\[\s*\]', adapter))
add("C1", c1, "adapter contains top-level \"xd\": [] and \"xd_zs\": []" if c1 else "could not find fixed empty xd/xd_zs", "medium")

# C2: whitelist missing xd/xd_zs
m = re.search(r"FIELD_WHITELIST\s*=\s*\{(?P<body>.*?)\n\}", adapter, re.S)
whitelist_body = m.group("body") if m else ""
c2 = ("xd" not in whitelist_body) and ("xd_zs" not in whitelist_body)
add("C2", c2, "FIELD_WHITELIST body does not contain xd/xd_zs" if c2 else "FIELD_WHITELIST appears to include xd or xd_zs", "medium")

# C3: tests only check bi whitelist
c3 = ('FIELD_WHITELIST["bi"]' in test_basic or "FIELD_WHITELIST['bi']" in test_basic) and not any(s in test_basic for s in ['FIELD_WHITELIST["meta"]', 'FIELD_WHITELIST["fx"]', 'FIELD_WHITELIST["bi_zs"]', 'FIELD_WHITELIST["beichi"]', 'FIELD_WHITELIST["signals"]', 'FIELD_WHITELIST["xd"]'])
add("C3", c3, "test_basic checks bi whitelist but no full-section schema validation was detected" if c3 else "full whitelist coverage may exist; inspect tests", "medium")

# C4: no full new_bars output
has_new_bars_key = re.search(r'"new_bars"\s*:', adapter) is not None
has_n_new_bars = re.search(r'"n_new_bars"\s*:', adapter) is not None
c4 = (not has_new_bars_key) and has_n_new_bars
add("C4", c4, "adapter has n_new_bars but no top-level new_bars list" if c4 else f"new_bars key detected={has_new_bars_key}, n_new_bars={has_n_new_bars}", "high")

# C5: no multi-level analyzer
multi_files = list(PKG.rglob("*multi*level*")) + list(PKG.rglob("multi_level_analyzer.py"))
contains_multilevel_func = "analyze_multi_level" in adapter + state + xd
c5 = not multi_files and not contains_multilevel_func
add("C5", c5, f"multi-level files={multi_files}, analyze_multi_level detected={contains_multilevel_func}", "high")

# C6: decide signature lacks position/prior_bsp
try:
    tree = ast.parse(state)
    decide_args = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "decide":
            decide_args = [a.arg for a in node.args.args]
            break
    c6 = "position" not in decide_args and "prior_bsp" not in decide_args and "context" not in decide_args
    add("C6", c6, f"decide args={decide_args}", "high")
except Exception as e:
    add("C6", False, f"failed to parse decide signature: {e}", "high")

# C7: simplified B3 logic pattern
c7 = bool(re.search(r'last_dir\s*==\s*["\']向上["\']\s+and\s+last_bi\[["\']low["\']\]\s*>\s*last_zs\[["\']zg["\']\]', state))
add("C7", c7, "B3 branch matches simplified last_dir == 向上 and last_bi['low'] > last_zs['zg']" if c7 else "did not detect that exact simplified B3 pattern", "high")

# C8: simplified B2 without prior_bsp
c8_pattern = bool(re.search(r'last_dir\s*==\s*["\']向下["\'].*last_bi\[["\']low["\']\]\s*>\s*last_zs\[["\']dd["\']', state, re.S))
c8_no_prior = "prior_bsp" not in state and "prior_1B" not in state and "one_buy" not in state.lower()
add("C8", c8_pattern and c8_no_prior, f"B2 simplified pattern={c8_pattern}; prior anchor/context detected={not c8_no_prior}", "high")

# C9: confirmed unreachable from compute_beichi
status_assignment = re.findall(r'status\s*=\s*([^\n]+)', adapter)
explicit_confirmed_assign = any("confirmed" in s and "suspected" not in s for s in status_assignment)
# It may include comments/whitelist; check assignments only.
c9 = any("suspected" in s and "none" in s for s in status_assignment) and not explicit_confirmed_assign
add("C9", c9, f"status assignments={status_assignment[:5]}; explicit_confirmed_assign={explicit_confirmed_assign}", "medium")

# C10: xd_segment declares experimental/not validated/default off
c10 = all(k in xd for k in ["未通过正确性验证", "默认不启用"])
add("C10", c10, "xd_segment header declares not validated and default off" if c10 else "xd_segment header does not clearly declare experimental status", "medium")

# D1: README version mismatch
c_d1 = "# 缠论分析交易系统 v1.0" in readme and "v1.0.2" not in readme.splitlines()[0]
add("D1", c_d1, f"README first line: {readme.splitlines()[0] if readme else 'missing'}", "low")

# D2: docs has Chinese filename
chinese_docs = [p.name for p in DOCS.glob("*") if re.search(r"[\u4e00-\u9fff]", p.name)]
add("D2", bool(chinese_docs), f"Chinese doc filenames: {chinese_docs}", "low")

# D3: duplicate root files in original zip
try:
    with zipfile.ZipFile(ORIGINAL_ZIP) as zf:
        names = zf.namelist()
    d3 = "xd_segment.py" in names and "bsp_state_machine.py" in names and any(n.endswith("chan_system_v1.0.2.zip") for n in names)
    add("D3", d3, f"top-level zip entries: {names}", "low")
except Exception as e:
    add("D3", False, f"cannot inspect original zip: {e}", "low")

# Extra: direction normalization in xd fixed
xd_has_dir_str = "def _dir_str" in xd and "D = [_dir_str" in xd
add("extra_xd_direction_fix", xd_has_dir_str, "xd_segment has _dir_str and precomputed D directions", "info")

# Extra: beichi-last-bi alignment in state
align_check = "leave_bi_idx" in state and "last_bi" in state and "bc = None" in state
add("extra_beichi_alignment_fix", align_check, "state machine nulls bc if leave_bi_idx mismatches last_bi", "info")

report = {
    "package_root": str(ROOT),
    "source_root": str(PKG),
    "results": RESULTS,
    "summary": {
        "total": len(RESULTS),
        "ok_true": sum(1 for r in RESULTS if r["ok"]),
        "ok_false": sum(1 for r in RESULTS if not r["ok"]),
    }
}

print(json.dumps(report, ensure_ascii=False, indent=2))

# 非零退出只用于严重语法失败；审计缺口被确认不是脚本失败。
syntax_fail = any(r["claim"] == "B1" and not r["ok"] for r in RESULTS)
raise SystemExit(1 if syntax_fail else 0)

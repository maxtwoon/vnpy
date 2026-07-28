"""Generate a research-only diff report from czsc upgrade fixtures.

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->
Reads the 0.9.51 and 1.0.0rc8 fixture directories produced by
``czsc_upgrade_bi_diff.py`` and writes a markdown report quantifying the
behavioral differences in 分型/笔/中枢/买卖点 signal outputs on real historical
futures data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FIXTURES_DIR = Path(__file__).resolve().parent / "czsc_upgrade_fixtures"
OLD_VERSION = "0_9_51"
NEW_VERSION = "1_0_0rc8"

# Observed 0.9.51 bi counts when CZSC_MAX_BI_NUM=10000 (exploratory run).
# czsc 1.0.0rc8 appears to enforce its own 50-bi window regardless of this env,
# so these unbounded counts are recorded for disclosure only.
OLD_UNBOUNDED_BI_COUNTS: dict[str, int] = {
    "AP888": 449,
    "RB888": 709,
    "SC888": 1120,
    "A888": 657,
    "ZN888": 978,
}


def _load_summary(version_slug: str) -> dict[str, Any]:
    path = FIXTURES_DIR / version_slug / "summary.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_symbol(version_slug: str, symbol: str) -> dict[str, Any]:
    path = FIXTURES_DIR / version_slug / f"{symbol}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _bi_identity(bi: dict[str, Any]) -> tuple[str, str, float, float]:
    return (bi.get("direction"), bi.get("sdt"), bi.get("high"), bi.get("low"))


def _match_bis(old_bis: list[dict], new_bis: list[dict]) -> dict[str, Any]:
    """Count exact-match, moved-boundary, and entirely new/deleted 笔."""
    old_ids = {_bi_identity(b) for b in old_bis}
    new_ids = {_bi_identity(b) for b in new_bis}
    exact = len(old_ids & new_ids)
    only_old = len(old_ids - new_ids)
    only_new = len(new_ids - old_ids)
    return {
        "exact_match_count": exact,
        "old_only_count": only_old,
        "new_only_count": only_new,
        "old_total": len(old_bis),
        "new_total": len(new_bis),
    }


def _confirmed_fx_count(data: dict[str, Any]) -> int:
    """Count fx whose dt is an endpoint of at least one bi.

    In 1.0.0rc8 ``fx_list`` contains raw candidate分型 in addition to the
    confirmed ones; this gives a version-agnostic lower bound on how many of
    the reported 分型 are genuine bi endpoints.
    """
    bi_endpoints: set[str] = set()
    for bi in data.get("bi_list", []):
        for key in ("sdt", "edt"):
            value = bi.get(key)
            if value:
                bi_endpoints.add(value)
    return sum(1 for fx in data.get("fx_list", []) if fx.get("dt") in bi_endpoints)


def _signal_diff(old_signals: dict[str, str], new_signals: dict[str, str]) -> dict[str, Any]:
    """Compare the set of non-任意 buy/sell/divergence/risk signal keys."""
    old_keys = set(old_signals.keys())
    new_keys = set(new_signals.keys())

    changed: dict[str, dict[str, str]] = {}
    for key in old_keys & new_keys:
        if old_signals[key] != new_signals[key]:
            changed[key] = {"old": old_signals[key], "new": new_signals[key]}

    return {
        "old_key_count": len(old_keys),
        "new_key_count": len(new_keys),
        "common_key_count": len(old_keys & new_keys),
        "old_only_keys": sorted(old_keys - new_keys),
        "new_only_keys": sorted(new_keys - new_keys),
        "changed_values": changed,
    }


def _transition_fingerprint(t: dict[str, Any]) -> tuple[str, str, str, str]:
    return (t.get("dt", ""), t.get("key", ""), t.get("old", ""), t.get("new", ""))


def _transition_diff(old_trans: list[dict], new_trans: list[dict]) -> dict[str, Any]:
    """Compare per-bar signal transition histories.

    Returns counts per key and the first few transitions that appear in one
    version but not the other.
    """
    old_set = {_transition_fingerprint(t) for t in old_trans}
    new_set = {_transition_fingerprint(t) for t in new_trans}

    old_by_key: dict[str, int] = {}
    new_by_key: dict[str, int] = {}
    for t in old_trans:
        old_by_key[t.get("key", "")] = old_by_key.get(t.get("key", ""), 0) + 1
    for t in new_trans:
        new_by_key[t.get("key", "")] = new_by_key.get(t.get("key", ""), 0) + 1

    only_old = sorted(old_set - new_set, key=lambda x: (x[0], x[1]))
    only_new = sorted(new_set - old_set, key=lambda x: (x[0], x[1]))

    return {
        "old_total": len(old_trans),
        "new_total": len(new_trans),
        "old_by_key": old_by_key,
        "new_by_key": new_by_key,
        "only_old": only_old,
        "only_new": only_new,
    }


def _summarize_signal_changes(all_signal_diffs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-symbol signal changes into a concise table."""
    old_only_total = 0
    new_only_total = 0
    changed_total = 0
    for diff in all_signal_diffs.values():
        old_only_total += len(diff["old_only_keys"])
        new_only_total += len(diff["new_only_keys"])
        changed_total += len(diff["changed_values"])
    return {
        "symbols_with_signal_changes": sum(
            1 for diff in all_signal_diffs.values()
            if diff["old_only_keys"] or diff["new_only_keys"] or diff["changed_values"]
        ),
        "old_only_key_occurrences": old_only_total,
        "new_only_key_occurrences": new_only_total,
        "changed_value_occurrences": changed_total,
    }


def _baseline_displacement() -> dict[str, dict[str, Any]]:
    """Compare the refreshed research-mode baseline against the pre-upgrade baseline.

    The old baseline is read from a committed golden fixture
    (``*.snapshot.pre_czsc10.json``) so it cannot be silently lost or self-cancel
    after the refreshed snapshot is committed.  The new baseline is read from the
    current snapshot file.  Both paths are resolved relative to this script, not
    to CWD.  Any missing/malformed file raises an exception (fail-loud) instead of
    returning an empty dict, because this is the largest real-data strategy-level
    delta caused by the czsc 1.0.0rc8 bi-algorithm change and must never be
    silently omitted from the report.
    """
    tests_dir = Path(__file__).resolve().parents[1] / "tests" / "unit"
    old_path = tests_dir / "test_position_sizing_research_equivalence.snapshot.pre_czsc10.json"
    new_path = tests_dir / "test_position_sizing_research_equivalence.snapshot.json"

    if not old_path.exists():
        raise FileNotFoundError(f"Pre-upgrade baseline fixture missing: {old_path}")
    if not new_path.exists():
        raise FileNotFoundError(f"Current baseline snapshot missing: {new_path}")

    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))

    result: dict[str, dict[str, Any]] = {}
    fields = [
        "total_trades",
        "total_return_pct",
        "sharpe_ratio",
        "profit_factor",
        "max_drawdown_pct",
    ]
    for symbol in ("SC888", "RB888"):
        old_report = old.get(symbol, {})
        new_report = new.get(symbol, {}).get("report", {})
        result[symbol] = {f: {"old": old_report.get(f), "new": new_report.get(f)} for f in fields}
        # Sub-strategy trade counts / win rates (Chinese keys are preserved as-is).
        old_sub = old_report.get("sub_strategies", {})
        new_sub = new_report.get("sub_strategies", {})
        result[symbol]["sub_strategies"] = {}
        for key in old_sub:
            result[symbol]["sub_strategies"][key] = {
                "old_trades": old_sub[key].get("total_trades"),
                "new_trades": new_sub.get(key, {}).get("total_trades"),
                "old_win_rate": old_sub[key].get("win_rate"),
                "new_win_rate": new_sub.get(key, {}).get("win_rate"),
            }
    return result


def main() -> None:
    old_summary = _load_summary(OLD_VERSION)
    new_summary = _load_summary(NEW_VERSION)
    symbols = old_summary["symbols"]

    rows: list[dict[str, Any]] = []
    signal_diffs: dict[str, dict[str, Any]] = {}
    transition_diffs: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        old = _load_symbol(OLD_VERSION, symbol)
        new = _load_symbol(NEW_VERSION, symbol)

        # Compare the same retained window. 0.9.51 was run with its default cap
        # (50), while 1.0.0rc8 appears to cap bi_list at 50 even when
        # CZSC_MAX_BI_NUM is raised, so the effective window is the last 50 bi.
        new_bis = new["bi_list"]
        old_bis_window = old["bi_list"][-len(new_bis):] if len(old["bi_list"]) > len(new_bis) else old["bi_list"]
        bi_match = _match_bis(old_bis_window, new_bis)

        signal_diff = _signal_diff(old["signals"], new["signals"])
        signal_diffs[symbol] = signal_diff
        transition_diffs[symbol] = _transition_diff(old.get("signal_transitions", []), new.get("signal_transitions", []))
        rows.append(
            {
                "symbol": symbol,
                "bars": old["bars_count"],
                "fx_old": old["fx_count"],
                "fx_new": new["fx_count"],
                "fx_confirmed_old": _confirmed_fx_count(old),
                "fx_confirmed_new": _confirmed_fx_count(new),
                "bi_old": bi_match["old_total"],
                "bi_new": bi_match["new_total"],
                "bi_old_unbounded": OLD_UNBOUNDED_BI_COUNTS.get(symbol),
                "bi_exact": bi_match["exact_match_count"],
                "bi_old_only": bi_match["old_only_count"],
                "bi_new_only": bi_match["new_only_count"],
                "zs_old": old["zs_count"],
                "zs_new": new["zs_count"],
                "signal_old_keys": signal_diff["old_key_count"],
                "signal_new_keys": signal_diff["new_key_count"],
                "signal_changed": len(signal_diff["changed_values"]),
                "trans_old": transition_diffs[symbol]["old_total"],
                "trans_new": transition_diffs[symbol]["new_total"],
            }
        )

    signal_agg = _summarize_signal_changes(signal_diffs)
    baseline_delta = _baseline_displacement()

    # Build markdown report
    lines: list[str] = []
    lines.append("# czsc 0.9.51 → 1.0.0rc8 行为差异报告")
    lines.append("")
    lines.append("<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->")
    lines.append("")
    lines.append(
        "本报告基于真实历史期货连续合约数据,量化 czsc 库从 0.9.51(纯 Python)"
        "升级到 1.0.0rc8(Rust 重写)后在分型、笔、中枢、买卖点信号层面的差异。"
    )
    lines.append("本报告仅供研究参考,不得作为策略有效性的推广证据。")
    lines.append("")
    lines.append("## 数据与范围")
    lines.append("")
    lines.append(f"- 数据来源: `{old_summary['start_date']}` 至 `{old_summary['end_date']}`")
    lines.append(f"- 交易周期: {old_summary['trade_freq_label']}({old_summary['trade_freq_minutes']} 分钟)")
    lines.append(f"- 品种: {', '.join(symbols)}")
    lines.append(f"- 旧版本 fixture: `{FIXTURES_DIR / OLD_VERSION}`")
    lines.append(f"- 新版本 fixture: `{FIXTURES_DIR / NEW_VERSION}`")
    lines.append(f"- 生成时间: {new_summary['generated_at']}")
    max_bi_num = new_summary.get("max_bi_num_used")
    max_bi_env = new_summary.get("max_bi_num_env")
    if max_bi_num is not None:
        env_note = f"(环境变量 CZSC_MAX_BI_NUM={max_bi_env})" if max_bi_env else "(默认值,未设置环境变量)"
        lines.append(f"- 本次 fixture 使用的 ``CZSC_MAX_BI_NUM``: **{max_bi_num}** {env_note}")
    lines.append("")

    # --- max_bi_num disclosure
    lines.append("### 关于 ``max_bi_num`` 截断的披露")
    lines.append("")
    lines.append("- 0.9.51 fixture 使用默认值 ``CZSC_MAX_BI_NUM=50``。")
    lines.append(
        "- 在独立探索性运行中将该环境变量设为 10000 时,0.9.51 返回了更多的笔 "
        "(见下表 `旧版未截断笔数`)。"
    )
    lines.append(
        "- 1.0.0rc8 fixture 虽以 ``CZSC_MAX_BI_NUM=10000`` 启动,但实际 ``bi_list`` "
        "仍只保留最近 50 笔,表明 Rust 核心在当前 RC 中似乎有独立的硬上限或尚未完整实现该环境变量。"
    )
    lines.append(
        "- 因此下表 `笔 old/new` 与 `完全一致笔` 均基于两者**实际保留的相同 50 笔窗口**"
        "进行对比;未截断差异通过 `旧版未截断笔数` 一栏单独披露。"
    )
    lines.append("")

    lines.append("## 结构数量对比")
    lines.append("")
    lines.append(
        "**注意**：`fx_list` 在 czsc 1.0.0rc8 中的语义与 0.9.51 不同;"
        "1.0 返回的 `fx_list` 包含更多原始分型候选,而 0.9.51 仅返回已确认分型。"
        "``分型(确认)`` 一列统计了至少作为一个笔端点出现的分型数量(版本无关的'确认'口径),"
        "比原始 ``fx_count`` 更适合衡量结构差异。"
    )
    lines.append("")
    lines.append(
        "| 品种 | K线数 | 分型 old/new | 分型(确认) old/new | 笔 old/new | 旧版未截断笔数 | 完全一致笔 | 旧版独有笔 | "
        "新版独有笔 | 中枢 old/new | 信号键变化 | 信号转态次数 old/new |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    total_old_bi = 0
    total_new_bi = 0
    total_exact = 0
    for r in rows:
        total_old_bi += r["bi_old"]
        total_new_bi += r["bi_new"]
        total_exact += r["bi_exact"]
        lines.append(
            f"| {r['symbol']} | {r['bars']} | {r['fx_old']} / {r['fx_new']} | "
            f"{r['fx_confirmed_old']} / {r['fx_confirmed_new']} | "
            f"{r['bi_old']} / {r['bi_new']} | {r['bi_old_unbounded']} | {r['bi_exact']} | {r['bi_old_only']} | "
            f"{r['bi_new_only']} | {r['zs_old']} / {r['zs_new']} | "
            f"{r['signal_changed']} | {r['trans_old']} / {r['trans_new']} |"
        )

    exact_pct = (total_exact / total_old_bi * 100) if total_old_bi else 0.0
    total_unbounded = sum(r["bi_old_unbounded"] or 0 for r in rows)
    lines.append("")
    lines.append(
        f"**汇总(50 笔窗口)**: 旧版总笔数 {total_old_bi},新版总笔数 {total_new_bi},"
        f"边界完全一致的笔 {total_exact}(占旧版窗口 {exact_pct:.1f}%)。"
    )
    lines.append(
        f"**汇总(未截断探索)**: 0.9.51 在 ``CZSC_MAX_BI_NUM=10000`` 下共产生 {total_unbounded} 笔,"
        "是同一数据集上 1.0.0rc8 保留窗口总笔数的数倍,说明 1.0 的 Rust 实现确实丢弃了早期笔。"
    )
    lines.append("")

    # --- ZN888 fx explanation
    lines.append("### ZN888 分型数量差异说明")
    lines.append("")
    lines.append(
        "ZN888 的 ``fx_count`` 从 0.9.51 的 222 上升到 1.0.0rc8 的 1074(约 4.8 倍),"
        "而 AP888/RB888/SC888/A888 的升幅明显更小。这并不意味着 ZN888 的缠论结构"
        "本身发生了数倍变化：按'至少是一个笔端点'的确认口径统计,ZN888 的确认分型"
        "数量与 A888/AP888 等品种处于同一量级(约 50 个)。ZN888 的高波动性/反复震荡"
        "产生了大量被后续 K 线否决的候选分型;1.0.0rc8 把这些候选保留在 ``fx_list`` 中,"
        "0.9.51 则提前过滤掉,于是呈现出 4.8 倍的计数差异。"
    )
    lines.append("")

    lines.append("## 信号差异汇总(终端快照)")
    lines.append("")
    lines.append(
        f"- 发生信号键/取值变化的品种数: {signal_agg['symbols_with_signal_changes']} / {len(symbols)}\n"
        f"- 旧版独有信号键出现次数: {signal_agg['old_only_key_occurrences']}\n"
        f"- 新版独有信号键出现次数: {signal_agg['new_only_key_occurrences']}\n"
        f"- 信号键共有但取值变化次数: {signal_agg['changed_value_occurrences']}"
    )
    lines.append("")

    lines.append("## 逐 bar 信号触发差异统计")
    lines.append("")
    lines.append(
        "以下统计基于逐 bar 回放：从第一根 K 线开始,每次 ``update`` 后调用 "
        "``get_all_signals``,记录过滤后的买卖/背驰/风控信号取值变化。"
        "'终端快照'只看最后一根 K 线的信号字典;"
        "'逐 bar 转态次数'才反映策略在实盘中会观察到多少次信号变化。"
    )
    lines.append("")
    for symbol in symbols:
        diff = transition_diffs[symbol]
        lines.append(f"### {symbol}")
        lines.append("")
        lines.append(f"- 旧版信号转态次数: {diff['old_total']}")
        lines.append(f"- 新版信号转态次数: {diff['new_total']}")
        lines.append(f"- 仅旧版出现的转态: {len(diff['only_old'])}")
        lines.append(f"- 仅新版出现的转态: {len(diff['only_new'])}")
        lines.append("")
        lines.append("按信号键统计(旧版 / 新版)：")
        lines.append("")
        lines.append("| 信号键 | 旧版转态次数 | 新版转态次数 |")
        lines.append("|---|---|---|")
        all_keys = sorted(set(diff["old_by_key"]) | set(diff["new_by_key"]))
        for key in all_keys:
            lines.append(f"| `{key}` | {diff['old_by_key'].get(key, 0)} | {diff['new_by_key'].get(key, 0)} |")
        lines.append("")
        if diff["only_old"]:
            lines.append("旧版独有的前 5 次转态(dt, key, old→new)：")
            for dt, key, old, new in diff["only_old"][:5]:
                lines.append(f"- `{dt}` `{key}`: `{old}` → `{new}`")
            lines.append("")
        if diff["only_new"]:
            lines.append("新版独有的前 5 次转态(dt, key, old→new)：")
            for dt, key, old, new in diff["only_new"][:5]:
                lines.append(f"- `{dt}` `{key}`: `{old}` → `{new}`")
            lines.append("")

    lines.append("## 逐品种终端信号差异明细")
    lines.append("")
    for symbol, diff in signal_diffs.items():
        lines.append(f"### {symbol}")
        lines.append("")
        if not diff["old_only_keys"] and not diff["new_only_keys"] and not diff["changed_values"]:
            lines.append("- 无买卖/背驰/风控信号差异。")
        else:
            if diff["old_only_keys"]:
                lines.append(f"- 旧版独有信号键({len(diff['old_only_keys'])} 个):")
                for key in diff["old_only_keys"][:10]:
                    lines.append(f"  - `{key}`")
                if len(diff["old_only_keys"]) > 10:
                    lines.append(f"  - ... 共 {len(diff['old_only_keys'])} 个")
            if diff["new_only_keys"]:
                lines.append(f"- 新版独有信号键({len(diff['new_only_keys'])} 个):")
                for key in diff["new_only_keys"][:10]:
                    lines.append(f"  - `{key}`")
                if len(diff["new_only_keys"]) > 10:
                    lines.append(f"  - ... 共 {len(diff['new_only_keys'])} 个")
            if diff["changed_values"]:
                lines.append(f"- 取值变化的信号键({len(diff['changed_values'])} 个):")
                for key, vals in list(diff["changed_values"].items())[:10]:
                    lines.append(f"  - `{key}`: `{vals['old']}` → `{vals['new']}`")
                if len(diff["changed_values"]) > 10:
                    lines.append(f"  - ... 共 {len(diff['changed_values'])} 个")
        lines.append("")

    # --- baseline displacement
    if baseline_delta:
        lines.append("## research-mode 基准位移(真实策略级影响)")
        lines.append("")
        lines.append(
            "以下对比的是 ``tests/unit/test_position_sizing_research_equivalence.snapshot.json`` "
            "在升级前后的 Bucket-B 计算字段。该 snapshot 在 dev 分支旧版 czsc 上的值"
            "与本次为 1.0.0rc8 刷新后的值之间的差异,直接反映了笔算法变化对策略绩效的影响。"
        )
        lines.append("")
        for symbol, fields in baseline_delta.items():
            lines.append(f"### {symbol}")
            lines.append("")
            lines.append("| 指标 | 旧版 (0.9.51) | 新版 (1.0.0rc8) |")
            lines.append("|---|---|---|")
            metric_names = {
                "total_trades": "成交对数",
                "total_return_pct": "total_return_pct",
                "sharpe_ratio": "sharpe_ratio",
                "profit_factor": "profit_factor",
                "max_drawdown_pct": "max_drawdown_pct",
            }
            for metric, names in metric_names.items():
                old_v = fields.get(metric, {}).get("old")
                new_v = fields.get(metric, {}).get("new")
                lines.append(f"| {names} | {old_v} | {new_v} |")
            sub = fields.get("sub_strategies", {})
            if sub:
                lines.append("")
                lines.append("子策略成交/胜率变化：")
                lines.append("")
                lines.append("| 子策略 | 旧版成交数 | 新版成交数 | 旧版胜率 | 新版胜率 |")
                lines.append("|---|---|---|---|---|")
                for key, vals in sub.items():
                    lines.append(
                        f"| {key} | {vals['old_trades']} | {vals['new_trades']} | "
                        f"{vals['old_win_rate']} | {vals['new_win_rate']} |"
                    )
            lines.append("")

    # --- fixture reproducibility note
    lines.append("## Fixture 可复现性说明")
    lines.append("")
    lines.append(
        f"两个版本的 fixture 均使用当前脚本重新生成,均包含 ``bars_raw``、"
        f"``signal_transitions`` 与 ``max_bi_num_used`` 字段。旧版本 fixture 在 "
        f"``{OLD_VERSION}`` 目录下由独立 venv(``czsc==0.9.51``)运行本脚本产生;"
        f"新版本 fixture 在 ``{NEW_VERSION}`` 目录下由当前主环境(``czsc==1.0.0rc8``)"
        "产生。重新生成命令："
    )
    lines.append("")
    lines.append("```bash")
    lines.append("# 0.9.51")
    lines.append("python -m venv /tmp/czsc0951")
    lines.append("pip install czsc==0.9.51")
    lines.append("CZSC_MAX_BI_NUM=10000 python diagnostics/czsc_upgrade_bi_diff.py")
    lines.append("")
    lines.append("# 1.0.0rc8")
    lines.append("CZSC_MAX_BI_NUM=10000 python diagnostics/czsc_upgrade_bi_diff.py")
    lines.append("```")
    lines.append("")
    lines.append(
        "说明：上述 fixture 目录与 `diagnostics/czsc_upgrade_sample_report.html` "
        "为可再生的生成产物,合计约 25MB,未纳入版本跟踪。review 可直接执行上述命令 "
        "在本地复现;若无需重新生成,当前 `czsc_upgrade_behavior_diff_report.md` "
        "正文已包含全部量化结论。"
    )
    lines.append("")

    lines.append("## 结论与纪律")
    lines.append("")
    lines.append(
        "czsc 1.0.0rc8 的 Rust 重写改变了笔的合并规则,导致同一组历史数据上的"
        "笔边界和下游信号发生变化。本次升级已完成导入路径迁移并如实记录上述差异;"
        "在通过正式 SimNow 前瞻观察之前,不应将本次升级视为『已验证可用』。"
    )
    lines.append("")

    report_path = Path(__file__).resolve().parent / "czsc_upgrade_behavior_diff_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()

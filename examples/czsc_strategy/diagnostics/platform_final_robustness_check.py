from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, _dominant_symbol  # noqa: E402
from diagnostics.check_platform_stability_goal import build_status  # noqa: E402
from diagnostics.platform_final_candidate import (  # noqa: E402
    CANDIDATE_NAME,
    DEFAULT_SC_SHORT_MULTIPLIER,
    FINAL_SC_MULTIPLIERS,
    final_candidate_params,
)
from diagnostics.portfolio_goal_evaluator import (  # noqa: E402
    GOAL,
    _evaluate_period,
    _fmt_num,
    _fmt_pct,
    _goal_status,
    _json_safe,
    _walk_forward,
    OOS_END,
    OOS_START,
)
from diagnostics.symbol_set_stability_scan import SYMBOL_SETS, _scaled_goal_status  # noqa: E402


BASE_ENGINE_COMMISSION_RATE = 0.0003
BASE_ENGINE_SLIPPAGE = 0.001

DATE_VARIANTS = {
    "base": (OOS_START, OOS_END),
    "start_plus_1m": ("2025-02-01", OOS_END),
    "start_minus_1m": ("2024-12-01", OOS_END),
    "end_minus_1m": (OOS_START, "2026-03-24"),
}


def _patch_candidate(
    multiplier: float = DEFAULT_SC_SHORT_MULTIPLIER,
    extra_params: dict[str, Any] | None = None,
    cost_factor: float = 1.0,
    use_cache: bool = True,
):
    import diagnostics.portfolio_goal_evaluator as evaluator

    original_scenario_params = evaluator._scenario_params
    original_run_symbol = evaluator._run_symbol
    original_engine = evaluator.BacktestEngine
    original_backtest = copy.deepcopy(BACKTEST_CONFIG)
    scenario = "final_candidate"
    cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    commission_rate = BASE_ENGINE_COMMISSION_RATE * cost_factor
    slippage = BASE_ENGINE_SLIPPAGE * cost_factor

    def scenario_params(name: str, symbol: str) -> dict[str, Any]:
        if name != scenario:
            return original_scenario_params(name, symbol)
        params = final_candidate_params(multiplier, symbol)
        if extra_params:
            params.update(copy.deepcopy(extra_params))
        return params

    evaluator._scenario_params = scenario_params
    def engine_with_costs(*args, **kwargs):
        kwargs.setdefault("commission_rate", commission_rate)
        kwargs.setdefault("slippage", slippage)
        return original_engine(*args, **kwargs)

    evaluator.BacktestEngine = engine_with_costs
    if use_cache:
        def run_symbol_cached(db_path: Path, symbol: str, start: str, end: str, name: str) -> dict[str, Any]:
            key = (symbol, start, end, name)
            if key not in cache:
                cache[key] = original_run_symbol(db_path, symbol, start, end, name)
            return copy.deepcopy(cache[key])

        evaluator._run_symbol = run_symbol_cached
    return evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest, scenario


def _restore_patch(
    evaluator,
    original_scenario_params,
    original_run_symbol,
    original_engine,
    original_backtest: dict[str, Any],
) -> None:
    evaluator._scenario_params = original_scenario_params
    evaluator._run_symbol = original_run_symbol
    evaluator.BacktestEngine = original_engine
    BACKTEST_CONFIG.clear()
    BACKTEST_CONFIG.update(original_backtest)


def _sc_neighbor(db_path: Path, cost_factor: float) -> dict[str, Any]:
    evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest, _ = _patch_candidate(cost_factor=cost_factor)
    payload: dict[str, Any] = {"cost_factor": cost_factor, "multipliers": {}}
    try:
        for multiplier in FINAL_SC_MULTIPLIERS:
            scenario = f"final_candidate_{multiplier:g}"

            def scenario_params(name: str, symbol: str, m: float = multiplier) -> dict[str, Any]:
                if name == scenario:
                    return final_candidate_params(m, symbol)
                return original_scenario_params(name, symbol)

            evaluator._scenario_params = scenario_params
            oos = _evaluate_period(db_path, DEFAULT_SYMBOLS, OOS_START, OOS_END, scenario)
            wf = _walk_forward(db_path, DEFAULT_SYMBOLS, scenario)
            payload["multipliers"][str(multiplier)] = {
                "out_sample": oos,
                "walk_forward": wf,
                "goal_status": _goal_status(oos, wf),
            }
    finally:
        _restore_patch(evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest)
    pass_count = sum(1 for row in payload["multipliers"].values() if row["goal_status"]["passed"])
    payload["pass_count"] = pass_count
    payload["total"] = len(payload["multipliers"])
    payload["passed"] = pass_count >= 4 and payload["total"] == 6
    return payload


def _symbol_sets(db_path: Path, cost_factor: float) -> dict[str, Any]:
    evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest, scenario = _patch_candidate(cost_factor=cost_factor)
    rows = {}
    try:
        for set_name in ["all5", "no_RB", "no_SC", "core_AP_A_ZN", "no_A", "no_ZN"]:
            symbols = SYMBOL_SETS[set_name]
            oos = _evaluate_period(db_path, symbols, OOS_START, OOS_END, scenario)
            wf = _walk_forward(db_path, symbols, scenario)
            rows[set_name] = {
                "symbols": symbols,
                "out_sample": oos,
                "walk_forward": wf,
                "goal_status": _scaled_goal_status(oos, wf, len(symbols)),
            }
    finally:
        _restore_patch(evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest)
    pass_count = sum(1 for row in rows.values() if row["goal_status"]["passed"])
    all5_wf = rows["all5"]["walk_forward"]
    return {
        "cost_factor": cost_factor,
        "rows": rows,
        "symbol_set_pass_count": pass_count,
        "symbol_set_total": len(rows),
        "symbol_sets_passed": pass_count >= 4 and len(rows) == 6,
        "all5_walk_forward_positive": all5_wf["positive_windows"],
        "all5_walk_forward_total": all5_wf["total_windows"],
        "all5_walk_forward_passed": all5_wf["positive_windows"] >= 7 and all5_wf["total_windows"] == 9,
    }


def _date_variants(db_path: Path, cost_factor: float) -> dict[str, Any]:
    evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest, scenario = _patch_candidate(cost_factor=cost_factor)
    rows = {}
    try:
        for name, (start, end) in DATE_VARIANTS.items():
            oos = _evaluate_period(db_path, DEFAULT_SYMBOLS, start, end, scenario)
            wf = _walk_forward(db_path, DEFAULT_SYMBOLS, scenario)
            status = _goal_status(oos, wf)
            rows[name] = {"start": start, "end": end, "out_sample": oos, "walk_forward": wf, "goal_status": status}
    finally:
        _restore_patch(evaluator, original_scenario_params, original_run_symbol, original_engine, original_backtest)
    pass_count = sum(1 for row in rows.values() if row["goal_status"]["passed"])
    return {"cost_factor": cost_factor, "rows": rows, "pass_count": pass_count, "total": len(rows), "passed": pass_count == len(rows)}


def _run_single_symbol(db_path: Path, requested_symbol: str, data_symbol: str, start: str, end: str) -> dict[str, Any]:
    original_strategy = copy.deepcopy(STRATEGY_CONFIG)
    table_name = f"{requested_symbol.lower()}_1M_raw"
    try:
        STRATEGY_CONFIG.update(final_candidate_params(0.75, requested_symbol))
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        return dict(report)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original_strategy)


def _dominant_symbol_audit(db_path: Path) -> dict[str, Any]:
    rows = {}
    with sqlite3.connect(db_path) as conn:
        for requested_symbol in DEFAULT_SYMBOLS:
            table = f"{requested_symbol.lower()}_1M_raw"
            items = conn.execute(
                f"select symbol, count(*) n, min(datetime), max(datetime) from {table} group by symbol order by n desc"
            ).fetchall()
            rows[requested_symbol] = [
                {"symbol": str(symbol), "rows": int(n), "start": str(start), "end": str(end)}
                for symbol, n, start, end in items
            ]
    ap_default = _dominant_symbol(db_path, "ap888_1M_raw", OOS_START, OOS_END)
    ap_lower = _run_single_symbol(db_path, "AP888", "ap888", "2026-02-24", OOS_END)
    ap_upper = _run_single_symbol(db_path, "AP888", "AP888", OOS_START, "2026-02-13")
    checks = {
        "dominant_symbol_present": bool(ap_default),
        "ap_lower_segment_runs": "error" not in ap_lower and ap_lower.get("total_trades", 0) > 0,
        "ap_upper_segment_runs": "error" not in ap_upper and ap_upper.get("total_trades", 0) > 0,
    }
    return {
        "symbol_distribution": rows,
        "ap_default_dominant_oos": ap_default,
        "ap_lower_segment": ap_lower,
        "ap_upper_segment": ap_upper,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_report(db_path: Path, sections: set[str], skip_heavy: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "candidate": CANDIDATE_NAME,
        "db_path": str(db_path),
        "goal": {
            "sc_neighbor_min": "4/6",
            "all5_walk_forward_min": "7/9",
            "symbol_sets_min": "4/6",
        },
    }
    payload["dominant_symbol_audit"] = _dominant_symbol_audit(db_path)
    if skip_heavy:
        payload["skipped_heavy"] = True
        return payload
    if "base_symbol_sets" in sections:
        payload["base_symbol_sets"] = _symbol_sets(db_path, cost_factor=1.0)
    if "cost2_symbol_sets" in sections:
        payload["cost_slippage_2x_symbol_sets"] = _symbol_sets(db_path, cost_factor=2.0)
    if "cost2_sc_neighbor" in sections:
        payload["cost_slippage_2x_sc_neighbor"] = _sc_neighbor(db_path, cost_factor=2.0)
    if "date_variants" in sections:
        payload["date_variants_2x"] = _date_variants(db_path, cost_factor=2.0)
    checks = {"dominant_symbol_audit": payload["dominant_symbol_audit"]["passed"]}
    if "base_symbol_sets" in payload:
        checks["base_symbol_sets"] = (
            payload["base_symbol_sets"]["symbol_sets_passed"]
            and payload["base_symbol_sets"]["all5_walk_forward_passed"]
        )
    if "cost_slippage_2x_symbol_sets" in payload:
        checks["cost_slippage_2x_symbol_sets"] = (
            payload["cost_slippage_2x_symbol_sets"]["symbol_sets_passed"]
            and payload["cost_slippage_2x_symbol_sets"]["all5_walk_forward_passed"]
        )
    if "cost_slippage_2x_sc_neighbor" in payload:
        checks["cost_slippage_2x_sc_neighbor"] = payload["cost_slippage_2x_sc_neighbor"]["passed"]
    if "date_variants_2x" in payload:
        checks["date_variants_2x"] = payload["date_variants_2x"]["passed"]
    payload["checks"] = checks
    payload["passed"] = all(checks.values())
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Final Candidate Robustness Check",
        "",
        f"- candidate: `{payload['candidate']}`",
        f"- db_path: `{payload['db_path']}`",
        "",
    ]
    if "base_symbol_sets" in payload or "cost_slippage_2x_symbol_sets" in payload:
        for key, title in [
            ("base_symbol_sets", "Base Symbol Sets"),
            ("cost_slippage_2x_symbol_sets", "Cost/Slippage 2x Symbol Sets"),
        ]:
            if key not in payload:
                continue
            item = payload[key]
            lines.extend([
                f"## {title}",
                "",
                f"- symbol sets: `{item['symbol_set_pass_count']}/{item['symbol_set_total']}`",
                f"- all5 WF: `{item['all5_walk_forward_positive']}/{item['all5_walk_forward_total']}`",
                "",
                "| set | pass | trades | PF | drawdown | sharpe | calmar | WF | failing_checks |",
                "|---|---|---:|---:|---:|---:|---:|---:|---|",
            ])
            for set_name, row in item["rows"].items():
                metrics = row["out_sample"]["metrics"]
                wf = row["walk_forward"]
                fails = [name for name, ok in row["goal_status"]["checks"].items() if not ok]
                lines.append(
                    f"| {set_name} | {row['goal_status']['passed']} | {_fmt_num(metrics['trades'], 0)} | "
                    f"{_fmt_num(metrics['profit_factor'])} | {_fmt_pct(metrics['max_drawdown_pct'])} | "
                    f"{_fmt_num(metrics['sharpe'])} | {_fmt_num(metrics['calmar'])} | "
                    f"{wf['positive_windows']}/{wf['total_windows']} | {', '.join(fails) or '-'} |"
                )
            lines.append("")
    if "cost_slippage_2x_sc_neighbor" in payload:
        sc = payload["cost_slippage_2x_sc_neighbor"]
        lines.extend([
            "## Cost/Slippage 2x SC Neighborhood",
            "",
            f"- pass count: `{sc['pass_count']}/{sc['total']}`",
            "",
            "| multiplier | pass | trades | PF | sharpe | calmar | WF |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ])
        for multiplier, row in sc["multipliers"].items():
            metrics = row["out_sample"]["metrics"]
            wf = row["walk_forward"]
            lines.append(
                f"| {multiplier} | {row['goal_status']['passed']} | {_fmt_num(metrics['trades'], 0)} | "
                f"{_fmt_num(metrics['profit_factor'])} | {_fmt_num(metrics['sharpe'])} | "
                f"{_fmt_num(metrics['calmar'])} | {wf['positive_windows']}/{wf['total_windows']} |"
            )
    if "date_variants_2x" in payload:
        lines.extend([
            "",
            "## Date Variants Under Cost/Slippage 2x",
            "",
            f"- pass count: `{payload['date_variants_2x']['pass_count']}/{payload['date_variants_2x']['total']}`",
            "",
            "| variant | pass | start | end | trades | PF | sharpe | calmar | WF |",
            "|---|---|---|---|---:|---:|---:|---:|---:|",
        ])
        for name, row in payload["date_variants_2x"]["rows"].items():
            metrics = row["out_sample"]["metrics"]
            wf = row["walk_forward"]
            lines.append(
                f"| {name} | {row['goal_status']['passed']} | {row['start']} | {row['end']} | "
                f"{_fmt_num(metrics['trades'], 0)} | {_fmt_num(metrics['profit_factor'])} | "
                f"{_fmt_num(metrics['sharpe'])} | {_fmt_num(metrics['calmar'])} | "
                f"{wf['positive_windows']}/{wf['total_windows']} |"
            )
        lines.append("")
    audit = payload["dominant_symbol_audit"]
    lines.extend([
        "## Dominant Symbol Audit",
        "",
        f"- passed: `{audit['passed']}`",
        f"- AP dominant in OOS: `{audit['ap_default_dominant_oos']}`",
        "",
        "| requested | symbol | rows | start | end |",
        "|---|---|---:|---|---|",
    ])
    for requested, rows in audit["symbol_distribution"].items():
        for row in rows:
            lines.append(f"| {requested} | {row['symbol']} | {row['rows']} | {row['start']} | {row['end']} |")
    if "checks" in payload:
        lines.extend([
            "",
            "## Final Checks",
            "",
            "| check | pass |",
            "|---|---|",
        ])
        for name, ok in payload["checks"].items():
            lines.append(f"| {name} | {ok} |")
        lines.append("")
        lines.append(f"**ROBUSTNESS PASSED: `{payload['passed']}`**")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run final candidate robustness checks.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--skip-heavy", action="store_true")
    parser.add_argument(
        "--sections",
        nargs="+",
        choices=["base_symbol_sets", "cost2_symbol_sets", "cost2_sc_neighbor", "date_variants"],
        default=["base_symbol_sets", "cost2_symbol_sets", "cost2_sc_neighbor", "date_variants"],
    )
    parser.add_argument("--out-json", type=Path, default=HERE / "platform_final_robustness_check.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "platform_final_robustness_check.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, sections=set(args.sections), skip_heavy=args.skip_heavy)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    if not args.skip_heavy and not payload.get("passed", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

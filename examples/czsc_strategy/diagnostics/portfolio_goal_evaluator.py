from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, _dominant_symbol
from diagnostics.rolling_candidate_matrix import WINDOWS
from diagnostics.strategy_execution_experiment_matrix import SECOND_BUY_FILTERS, TRAILING_OVERRIDES


FULL_START = "2022-01-01"
FULL_END = "2026-04-24"
OOS_START = "2025-01-01"
OOS_END = "2026-04-24"

GOAL = {
    "min_trades": 100,
    "min_profit_factor": 1.2,
    "max_drawdown_pct": 20.0,
    "min_sharpe": 0.5,
    "min_calmar": 0.5,
    "min_positive_walk_forward_ratio": 2 / 3,
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _scenario_params(name: str, symbol: str) -> dict[str, Any]:
    if name == "baseline":
        return {}
    if name == "baseline_short":
        return {"enable_short": True}
    if name == "second_buy_filters":
        return copy.deepcopy(SECOND_BUY_FILTERS)
    if name == "trailing_overrides":
        return copy.deepcopy(TRAILING_OVERRIDES)
    if name in {
        "combined", "expanded", "combined_short", "expanded_short",
        "expanded_short_rb_sc", "expanded_short_sc", "expanded_short_rb",
        "expanded_short_sc_half", "expanded_short_sc_light", "expanded_short_sc_085",
        "expanded_short_sc_0847",
    }:
        params = copy.deepcopy(SECOND_BUY_FILTERS)
        params.update(copy.deepcopy(TRAILING_OVERRIDES))
        if name in {"combined_short", "expanded_short"}:
            params["enable_short"] = True
        if name == "expanded_short_rb_sc":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["RB888", "SC888"]
        if name == "expanded_short_sc":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["SC888"]
        if name == "expanded_short_sc_half":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["SC888"]
            params["pos_1sell"] = 0.05
            params["pos_3sell"] = 0.15
        if name == "expanded_short_sc_085":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["SC888"]
            params["pos_1sell"] = 0.085
            params["pos_3sell"] = 0.255
        if name == "expanded_short_sc_0847":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["SC888"]
            params["pos_1sell"] = 0.0847
            params["pos_3sell"] = 0.2541
        if name == "expanded_short_sc_light":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["SC888"]
            params["pos_1sell"] = 0.03
            params["pos_3sell"] = 0.09
        if name == "expanded_short_rb":
            params["enable_short"] = True
            params["enable_short_symbols"] = ["RB888"]
        if name.startswith("expanded") and symbol in {"AP888", "A888"}:
            params["max_2buy_entry_vs_anchor_pct"] = None
        return params
    raise ValueError(f"unsupported scenario: {name}")


def _research_symbol_key(symbol: str) -> str:
    return "".join(ch for ch in str(symbol).upper() if ch.isalnum())


def _symbol_position_override(symbol: str | None, config_key: str) -> float | None:
    if symbol is None:
        return None
    overrides = STRATEGY_CONFIG.get("symbol_position_overrides") or {}
    item = overrides.get(_research_symbol_key(symbol), None)
    if isinstance(item, dict) and config_key in item:
        return float(item[config_key])
    return None


def _strategy_weight(strategy: str, symbol: str | None = None) -> float:
    if "一买" in strategy or "涓€涔" in strategy:
        return _symbol_position_override(symbol, "pos_1buy") or float(STRATEGY_CONFIG.get("pos_1buy", 0.10))
    if "二买" in strategy or "浜屼拱" in strategy:
        return _symbol_position_override(symbol, "pos_2buy") or float(STRATEGY_CONFIG.get("pos_2buy", 0.20))
    if "三买" in strategy or "涓変拱" in strategy:
        return _symbol_position_override(symbol, "pos_3buy") or float(STRATEGY_CONFIG.get("pos_3buy", 0.30))
    if "一卖" in strategy or "涓€鍗" in strategy:
        return _symbol_position_override(symbol, "pos_1sell") or float(STRATEGY_CONFIG.get("pos_1sell", 0.10))
    if "二卖" in strategy or "浜屽崠" in strategy:
        return _symbol_position_override(symbol, "pos_2sell") or float(STRATEGY_CONFIG.get("pos_2sell", 0.20))
    if "三卖" in strategy or "涓夊崠" in strategy:
        return _symbol_position_override(symbol, "pos_3sell") or float(STRATEGY_CONFIG.get("pos_3sell", 0.30))
    return 0.10


def _run_symbol(db_path: Path, symbol: str, start: str, end: str, scenario: str) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    table_name = f"{symbol.lower()}_1M_raw"
    data_symbol = _dominant_symbol(db_path, table_name, start, end)
    try:
        STRATEGY_CONFIG.update(copy.deepcopy(_scenario_params(scenario, symbol)))
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        trades = engine.strategy.get_combined_trades()
        for trade in trades:
            trade["requested_symbol"] = symbol
            trade["weighted_pnl_pct"] = (
                float(trade["pnl_pct"]) * _strategy_weight(str(trade["strategy"]), symbol) / len(DEFAULT_SYMBOLS)
            )
        equity = pd.Series(
            [x["equity"] / engine.initial_capital for x in engine.equity_curve],
            index=[x["dt"] for x in engine.equity_curve],
            name=symbol,
        )
        daily_equity = equity.groupby(equity.index.map(lambda dt: dt.date())).last()
        raw_close = pd.Series(
            [x.close for x in engine.bars],
            index=[x.dt for x in engine.bars],
            name=symbol,
        )
        daily_close = raw_close.groupby(raw_close.index.map(lambda dt: dt.date())).last()
        bh = daily_close / daily_close.iloc[0] if len(daily_close) else pd.Series(dtype=float, name=symbol)
        return {
            "report": report,
            "trades": trades,
            "daily_equity": daily_equity,
            "buy_hold": bh,
        }
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _portfolio_curve(curves: list[pd.Series]) -> pd.Series:
    if not curves:
        return pd.Series(dtype=float)
    df = pd.concat(curves, axis=1).sort_index().ffill().dropna(how="any")
    if df.empty:
        return pd.Series(dtype=float)
    return df.mean(axis=1)


def _curve_metrics(curve: pd.Series) -> dict[str, float]:
    if curve.empty or len(curve) < 2:
        return {"return_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0, "calmar": 0.0}
    total_return = float(curve.iloc[-1] / curve.iloc[0] - 1)
    peak = curve.cummax()
    dd = (peak - curve) / peak
    max_dd = float(dd.max()) if len(dd) else 0.0
    returns = curve.pct_change().dropna()
    sharpe = float((returns.mean() / returns.std()) * np.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    years = max(len(curve) / 252, 1 / 252)
    annual_return = float((curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1)
    calmar = annual_return / max_dd if max_dd > 0 else (float("inf") if annual_return > 0 else 0.0)
    return {
        "return_pct": total_return * 100,
        "max_drawdown_pct": max_dd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
    }


def _trade_metrics(trades: list[dict[str, Any]]) -> dict[str, float | int]:
    weighted = [float(t["weighted_pnl_pct"]) for t in trades]
    wins = [x for x in weighted if x > 0]
    losses = [x for x in weighted if x <= 0]
    loss_sum = abs(sum(losses))
    return {
        "trades": len(trades),
        "profit_factor": sum(wins) / loss_sum if loss_sum else float("inf"),
        "weighted_trade_return_pct": sum(weighted) * 100,
    }


def _evaluate_period(db_path: Path, symbols: list[str], start: str, end: str, scenario: str) -> dict[str, Any]:
    rows = {}
    all_trades: list[dict[str, Any]] = []
    curves = []
    bh_curves = []
    for symbol in symbols:
        row = _run_symbol(db_path, symbol, start, end, scenario)
        rows[symbol] = {
            "report": row["report"],
            "trade_count": len(row["trades"]),
        }
        all_trades.extend(row["trades"])
        curves.append(row["daily_equity"])
        bh_curves.append(row["buy_hold"])
    strategy_curve = _portfolio_curve(curves)
    bh_curve = _portfolio_curve(bh_curves)
    metrics = _curve_metrics(strategy_curve)
    metrics.update(_trade_metrics(all_trades))
    benchmark = _curve_metrics(bh_curve)
    metrics["risk_adjusted_better_than_buy_hold"] = (
        metrics["sharpe"] > benchmark["sharpe"] and metrics["calmar"] > benchmark["calmar"]
    )
    return {
        "start": start,
        "end": end,
        "scenario": scenario,
        "symbols": rows,
        "metrics": metrics,
        "buy_hold": benchmark,
    }


def _walk_forward(db_path: Path, symbols: list[str], scenario: str) -> dict[str, Any]:
    rows = {}
    positive = 0
    for name, (start, end) in WINDOWS.items():
        item = _evaluate_period(db_path, symbols, start, end, scenario)
        rows[name] = item["metrics"]
        if item["metrics"]["return_pct"] > 0:
            positive += 1
    total = len(WINDOWS)
    return {
        "positive_windows": positive,
        "total_windows": total,
        "positive_ratio": positive / total if total else 0,
        "windows": rows,
    }


def _goal_status(oos: dict[str, Any], wf: dict[str, Any]) -> dict[str, Any]:
    m = oos["metrics"]
    checks = {
        "trades_ge_100": m["trades"] >= GOAL["min_trades"],
        "pf_ge_1_2": m["profit_factor"] >= GOAL["min_profit_factor"],
        "drawdown_le_20": m["max_drawdown_pct"] <= GOAL["max_drawdown_pct"],
        "sharpe_ge_0_5": m["sharpe"] >= GOAL["min_sharpe"],
        "calmar_ge_0_5": m["calmar"] >= GOAL["min_calmar"],
        "walk_forward_ge_2_3": wf["positive_ratio"] >= GOAL["min_positive_walk_forward_ratio"],
        "risk_adjusted_gt_buy_hold": bool(m["risk_adjusted_better_than_buy_hold"]),
    }
    return {"checks": checks, "passed": all(checks.values())}


def build_report(db_path: Path, symbols: list[str], scenario: str) -> dict[str, Any]:
    full = _evaluate_period(db_path, symbols, FULL_START, FULL_END, scenario)
    oos = _evaluate_period(db_path, symbols, OOS_START, OOS_END, scenario)
    wf = _walk_forward(db_path, symbols, scenario)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "symbols": symbols,
        "scenario": scenario,
        "goal": GOAL,
        "full": full,
        "out_sample": oos,
        "walk_forward": wf,
        "goal_status": _goal_status(oos, wf),
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    oos = payload["out_sample"]["metrics"]
    bh = payload["out_sample"]["buy_hold"]
    checks = payload["goal_status"]["checks"]
    lines = [
        "# Portfolio Goal Evaluation",
        "",
        f"- scenario: `{payload['scenario']}`",
        f"- symbols: `{', '.join(payload['symbols'])}`",
        "- portfolio: five-symbol equal weight",
        "- costs: strategy engine commission/slippage are included",
        "",
        "## Out-Of-Sample Gate",
        "",
        "| metric | strategy | target / benchmark | pass |",
        "|---|---:|---:|---|",
        f"| trades | {_fmt_num(oos['trades'], 0)} | >= 100 | {checks['trades_ge_100']} |",
        f"| profit_factor | {_fmt_num(oos['profit_factor'])} | >= 1.20 | {checks['pf_ge_1_2']} |",
        f"| max_drawdown | {_fmt_pct(oos['max_drawdown_pct'])} | <= 20.00% | {checks['drawdown_le_20']} |",
        f"| sharpe | {_fmt_num(oos['sharpe'])} | >= 0.50 | {checks['sharpe_ge_0_5']} |",
        f"| calmar | {_fmt_num(oos['calmar'])} | >= 0.50 | {checks['calmar_ge_0_5']} |",
        f"| walk_forward_positive_ratio | {_fmt_pct(payload['walk_forward']['positive_ratio'] * 100)} | >= 66.67% | {checks['walk_forward_ge_2_3']} |",
        f"| risk_adjusted_vs_buy_hold | sharpe {_fmt_num(oos['sharpe'])} / calmar {_fmt_num(oos['calmar'])} | bh sharpe {_fmt_num(bh['sharpe'])} / bh calmar {_fmt_num(bh['calmar'])} | {checks['risk_adjusted_gt_buy_hold']} |",
        "",
        f"**GOAL PASSED: `{payload['goal_status']['passed']}`**",
        "",
        "## Full Sample",
        "",
        "| return | drawdown | sharpe | calmar | trades | PF |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {_fmt_pct(payload['full']['metrics']['return_pct'])} | {_fmt_pct(payload['full']['metrics']['max_drawdown_pct'])} | "
        f"{_fmt_num(payload['full']['metrics']['sharpe'])} | {_fmt_num(payload['full']['metrics']['calmar'])} | "
        f"{_fmt_num(payload['full']['metrics']['trades'], 0)} | {_fmt_num(payload['full']['metrics']['profit_factor'])} |",
        "",
        "## Walk Forward",
        "",
        "| window | return | drawdown | sharpe | calmar | trades | PF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in payload["walk_forward"]["windows"].items():
        lines.append(
            f"| {name} | {_fmt_pct(row['return_pct'])} | {_fmt_pct(row['max_drawdown_pct'])} | "
            f"{_fmt_num(row['sharpe'])} | {_fmt_num(row['calmar'])} | {_fmt_num(row['trades'], 0)} | {_fmt_num(row['profit_factor'])} |"
        )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the five-symbol portfolio against the hard goal gate.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--scenario", default="expanded")
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("portfolio_goal_evaluation.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("portfolio_goal_evaluation.md"))
    args = parser.parse_args()

    payload = build_report(args.db_path, args.symbols, args.scenario)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"goal_passed={payload['goal_status']['passed']}")


if __name__ == "__main__":
    main()

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
from diagnostics.backtest_matrix_report import _dominant_symbol
from diagnostics.rolling_candidate_matrix import WINDOWS
from diagnostics.portfolio_goal_evaluator import _fmt_num, _fmt_pct, _json_safe, _strategy_weight
from diagnostics.sc_short_weight_neighborhood import params_for_multiplier


NO_A_SYMBOLS = ["AP888", "RB888", "SC888", "ZN888"]
OOS_START = "2025-01-01"
OOS_END = "2026-04-24"


def _candidate_params() -> dict[str, Any]:
    params = params_for_multiplier(0.75, "AP888")
    params.update({
        "block_1buy_daily_down": True,
        "enable_short_symbols": ["SC888", "A888", "ZN888"],
        "symbol_position_overrides": {
            "A888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03},
            "ZN888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03},
        },
    })
    trailing = copy.deepcopy(params.get("trailing_overrides") or {})
    trailing.update({
            "A888": {"trailing_start_bp": 250, "trailing_drawback_pct": 0.20},
            "AP888": {"trailing_start_bp": 250, "trailing_drawback_pct": 0.20},
    })
    params["trailing_overrides"] = trailing
    return params


def _curve_metrics(curve: pd.Series) -> dict[str, float]:
    if curve.empty or len(curve) < 2:
        return {"return_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0, "calmar": 0.0}
    total_return = float(curve.iloc[-1] / curve.iloc[0] - 1)
    peak = curve.cummax()
    drawdown = (peak - curve) / peak
    max_drawdown = float(drawdown.max()) if len(drawdown) else 0.0
    returns = curve.pct_change().dropna()
    sharpe = float((returns.mean() / returns.std()) * np.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0.0
    years = max(len(curve) / 252, 1 / 252)
    annual_return = float((curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1)
    calmar = annual_return / max_drawdown if max_drawdown > 0 else (float("inf") if annual_return > 0 else 0.0)
    return {
        "return_pct": total_return * 100,
        "max_drawdown_pct": max_drawdown * 100,
        "sharpe": sharpe,
        "calmar": calmar,
    }


def _portfolio_curve(curves: list[pd.Series]) -> pd.Series:
    if not curves:
        return pd.Series(dtype=float)
    df = pd.concat(curves, axis=1).sort_index().ffill().dropna(how="any")
    if df.empty:
        return pd.Series(dtype=float)
    return df.mean(axis=1)


def _trade_stats(trades: list[dict[str, Any]], symbol: str) -> dict[str, Any]:
    rows: dict[str, dict[str, float | int]] = {}
    for trade in trades:
        strategy = str(trade.get("strategy", ""))
        item = rows.setdefault(strategy, {"trades": 0, "weighted_pnl_pct": 0.0, "raw_pnl_pct": 0.0})
        item["trades"] = int(item["trades"]) + 1
        item["raw_pnl_pct"] = float(item["raw_pnl_pct"]) + float(trade.get("pnl_pct", 0.0)) * 100
        item["weighted_pnl_pct"] = (
            float(item["weighted_pnl_pct"])
            + float(trade.get("pnl_pct", 0.0)) * _strategy_weight(strategy, symbol) * 100
        )
    return rows


def _run_symbol(db_path: Path, symbol: str, start: str, end: str, params: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    table_name = f"{symbol.lower()}_1M_raw"
    data_symbol = _dominant_symbol(db_path, table_name, start, end)
    try:
        STRATEGY_CONFIG.update(copy.deepcopy(params))
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        equity = pd.Series(
            [x["equity"] / engine.initial_capital for x in engine.equity_curve],
            index=[x["dt"] for x in engine.equity_curve],
            name=symbol,
        )
        daily_equity = equity.groupby(equity.index.map(lambda dt: dt.date())).last()
        close = pd.Series([x.close for x in engine.bars], index=[x.dt for x in engine.bars], name=symbol)
        daily_close = close.groupby(close.index.map(lambda dt: dt.date())).last()
        buy_hold = daily_close / daily_close.iloc[0] if len(daily_close) else pd.Series(dtype=float, name=symbol)
        trades = engine.strategy.get_combined_trades()
        return {
            "data_symbol": data_symbol,
            "report": report,
            "daily_equity": daily_equity,
            "buy_hold": buy_hold,
            "trades": trades,
            "sub_strategy_trade_stats": _trade_stats(trades, symbol),
        }
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _period_report(db_path: Path, symbols: list[str], start: str, end: str, params: dict[str, Any]) -> dict[str, Any]:
    rows = {}
    strategy_curves = []
    buy_hold_curves = []
    for symbol in symbols:
        row = _run_symbol(db_path, symbol, start, end, params)
        strategy_curves.append(row["daily_equity"])
        buy_hold_curves.append(row["buy_hold"])
        rows[symbol] = {
            "data_symbol": row["data_symbol"],
            "strategy_metrics": _curve_metrics(row["daily_equity"]),
            "buy_hold_metrics": _curve_metrics(row["buy_hold"]),
            "report": row["report"],
            "sub_strategy_trade_stats": row["sub_strategy_trade_stats"],
        }
    strategy_curve = _portfolio_curve(strategy_curves)
    buy_hold_curve = _portfolio_curve(buy_hold_curves)
    metrics = _curve_metrics(strategy_curve)
    bh_metrics = _curve_metrics(buy_hold_curve)
    return {
        "start": start,
        "end": end,
        "portfolio": {
            "strategy_metrics": metrics,
            "buy_hold_metrics": bh_metrics,
            "risk_adjusted_better_than_buy_hold": metrics["sharpe"] > bh_metrics["sharpe"]
            and metrics["calmar"] > bh_metrics["calmar"],
        },
        "symbols": rows,
    }


def build_report(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    params = _candidate_params()
    windows = {
        "OOS": (OOS_START, OOS_END),
        **WINDOWS,
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": "sc075_a_zn010 + A/AP trailing 250/0.20",
        "symbols": symbols,
        "params": params,
        "periods": {
            name: _period_report(db_path, symbols, start, end, params)
            for name, (start, end) in windows.items()
        },
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# no_A Failure Attribution",
        "",
        f"- candidate: `{payload['candidate']}`",
        f"- symbols: `{', '.join(payload['symbols'])}`",
        "",
        "## Portfolio Windows",
        "",
        "| window | strategy_ret | strategy_sharpe | strategy_calmar | bh_ret | bh_sharpe | bh_calmar | risk_adj_gt_bh |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, period in payload["periods"].items():
        m = period["portfolio"]["strategy_metrics"]
        bh = period["portfolio"]["buy_hold_metrics"]
        lines.append(
            f"| {name} | {_fmt_pct(m['return_pct'])} | {_fmt_num(m['sharpe'])} | {_fmt_num(m['calmar'])} | "
            f"{_fmt_pct(bh['return_pct'])} | {_fmt_num(bh['sharpe'])} | {_fmt_num(bh['calmar'])} | "
            f"{period['portfolio']['risk_adjusted_better_than_buy_hold']} |"
        )
    lines.extend(["", "## OOS By Symbol", ""])
    oos = payload["periods"]["OOS"]
    lines.extend([
        "| symbol | strategy_ret | strategy_sharpe | strategy_calmar | bh_ret | bh_sharpe | bh_calmar | trades | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for symbol, row in oos["symbols"].items():
        m = row["strategy_metrics"]
        bh = row["buy_hold_metrics"]
        report = row["report"]
        lines.append(
            f"| {symbol} | {_fmt_pct(m['return_pct'])} | {_fmt_num(m['sharpe'])} | {_fmt_num(m['calmar'])} | "
            f"{_fmt_pct(bh['return_pct'])} | {_fmt_num(bh['sharpe'])} | {_fmt_num(bh['calmar'])} | "
            f"{report.get('total_trades', 0)} | {_fmt_num(report.get('profit_factor', 0))} |"
        )
    lines.extend(["", "## OOS Sub-Strategy Weighted PnL", ""])
    lines.extend([
        "| symbol | strategy | trades | weighted_pnl | raw_pnl |",
        "|---|---|---:|---:|---:|",
    ])
    for symbol, row in oos["symbols"].items():
        stats = row["sub_strategy_trade_stats"]
        for strategy, item in sorted(stats.items(), key=lambda kv: float(kv[1]["weighted_pnl_pct"])):
            lines.append(
                f"| {symbol} | {strategy} | {item['trades']} | "
                f"{_fmt_pct(item['weighted_pnl_pct'])} | {_fmt_pct(item['raw_pnl_pct'])} |"
            )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute the no_A risk-adjusted failure for the current best candidate.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=NO_A_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("no_a_failure_attribution.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("no_a_failure_attribution.md"))
    args = parser.parse_args()

    payload = build_report(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, _dominant_symbol  # noqa: E402
from diagnostics.platform_final_candidate import CANDIDATE_NAME, final_candidate_params  # noqa: E402
from diagnostics.platform_final_robustness_check import BASE_ENGINE_COMMISSION_RATE, BASE_ENGINE_SLIPPAGE  # noqa: E402
from diagnostics.portfolio_goal_evaluator import _json_safe, _strategy_weight  # noqa: E402


FULL_START = "2022-01-01"
FULL_END = "2026-04-24"
OOS_START = "2025-01-01"
OOS_END = "2026-04-24"


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


def _run_symbol(db_path: Path, symbol: str, start: str, end: str, cost_factor: float) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    table_name = f"{symbol.lower()}_1M_raw"
    data_symbol = _dominant_symbol(db_path, table_name, start, end)
    try:
        STRATEGY_CONFIG.update(final_candidate_params(symbol=symbol))
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
            commission_rate=BASE_ENGINE_COMMISSION_RATE * cost_factor,
            slippage=BASE_ENGINE_SLIPPAGE * cost_factor,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        equity = pd.DataFrame(engine.equity_curve)
        equity["symbol"] = symbol
        trades = []
        for trade in engine.strategy.get_combined_trades():
            item = dict(trade)
            item["requested_symbol"] = symbol
            item["data_symbol"] = data_symbol
            item["weighted_pnl_pct"] = (
                float(item["pnl_pct"]) * _strategy_weight(str(item["strategy"]), symbol) * 100 / len(DEFAULT_SYMBOLS)
            )
            trades.append(item)
        return {
            "symbol": symbol,
            "data_symbol": data_symbol,
            "report": dict(report),
            "equity_curve": equity,
            "trades": trades,
        }
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _daily_portfolio(symbol_rows: dict[str, dict[str, Any]]) -> pd.DataFrame:
    curves = []
    exposures = []
    for symbol, row in symbol_rows.items():
        eq = row["equity_curve"].copy()
        if eq.empty:
            continue
        eq["date"] = pd.to_datetime(eq["dt"]).dt.date
        daily = eq.groupby("date").last()
        curves.append((daily["equity"] / daily["equity"].iloc[0]).rename(symbol))
        exp = daily[["long_exposure", "short_exposure", "net_exposure", "gross_exposure", "both_long_short"]].copy()
        exp.columns = pd.MultiIndex.from_product([[symbol], exp.columns])
        exposures.append(exp)
    if not curves:
        return pd.DataFrame()
    curve_df = pd.concat(curves, axis=1).sort_index().ffill().dropna(how="any")
    out = pd.DataFrame(index=curve_df.index)
    out["equity"] = curve_df.mean(axis=1)
    out["daily_return"] = out["equity"].pct_change().fillna(0.0)
    if exposures:
        exp_df = pd.concat(exposures, axis=1).sort_index().ffill().reindex(out.index).fillna(0.0)
        for col in ["long_exposure", "short_exposure", "gross_exposure"]:
            out[col] = sum(exp_df[(symbol, col)] for symbol in symbol_rows if (symbol, col) in exp_df.columns) / len(symbol_rows)
        out["net_exposure"] = sum(exp_df[(symbol, "net_exposure")] for symbol in symbol_rows if (symbol, "net_exposure") in exp_df.columns) / len(symbol_rows)
        both_cols = [(symbol, "both_long_short") for symbol in symbol_rows if (symbol, "both_long_short") in exp_df.columns]
        out["both_long_short_symbols"] = exp_df[both_cols].sum(axis=1) if both_cols else 0
    return out


def _max_consecutive_losses(daily: pd.DataFrame) -> dict[str, Any]:
    streak = 0
    max_streak = 0
    current_loss = 0.0
    max_loss = 0.0
    end_date = None
    for date, ret in daily["daily_return"].items():
        if ret < 0:
            streak += 1
            current_loss += float(ret)
            if streak > max_streak:
                max_streak = streak
                max_loss = current_loss
                end_date = date
        else:
            streak = 0
            current_loss = 0.0
    return {"days": max_streak, "cumulative_return_pct": max_loss * 100, "end_date": str(end_date) if end_date else None}


def _drawdown_stats(daily: pd.DataFrame) -> dict[str, Any]:
    if daily.empty:
        return {"max_drawdown_pct": 0.0, "max_recovery_days": 0}
    equity = daily["equity"]
    peak = equity.cummax()
    dd = equity / peak - 1
    max_dd = float(dd.min()) * 100
    max_recovery = 0
    underwater_start = None
    for date, value in dd.items():
        if value < 0 and underwater_start is None:
            underwater_start = date
        if value >= 0 and underwater_start is not None:
            max_recovery = max(max_recovery, (pd.Timestamp(date) - pd.Timestamp(underwater_start)).days)
            underwater_start = None
    if underwater_start is not None:
        max_recovery = max(max_recovery, (pd.Timestamp(daily.index[-1]) - pd.Timestamp(underwater_start)).days)
    return {"max_drawdown_pct": max_dd, "max_recovery_days": max_recovery}


def _concentration(trades: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, float] = defaultdict(float)
    for trade in trades:
        grouped[str(trade.get(key, ""))] += float(trade.get("weighted_pnl_pct", 0.0))
    total_abs = sum(abs(v) for v in grouped.values())
    rows = [
        {"name": name, "weighted_pnl_pct": value, "abs_share": abs(value) / total_abs if total_abs else 0.0}
        for name, value in grouped.items()
    ]
    rows.sort(key=lambda x: abs(float(x["weighted_pnl_pct"])), reverse=True)
    top1 = rows[0]["abs_share"] if rows else 0.0
    top3 = sum(float(row["abs_share"]) for row in rows[:3])
    return {"top1_abs_share": top1, "top3_abs_share": top3, "rows": rows}


def _risk_metrics(daily: pd.DataFrame, trades: list[dict[str, Any]]) -> dict[str, Any]:
    if daily.empty:
        return {}
    worst_day = daily["daily_return"].idxmin()
    best_day = daily["daily_return"].idxmax()
    return {
        "total_return_pct": (float(daily["equity"].iloc[-1] / daily["equity"].iloc[0]) - 1) * 100,
        "max_single_day_loss_pct": float(daily.loc[worst_day, "daily_return"]) * 100,
        "max_single_day_loss_date": str(worst_day),
        "max_single_day_gain_pct": float(daily.loc[best_day, "daily_return"]) * 100,
        "max_single_day_gain_date": str(best_day),
        "max_consecutive_loss": _max_consecutive_losses(daily),
        **_drawdown_stats(daily),
        "max_gross_exposure": float(daily.get("gross_exposure", pd.Series([0])).max()),
        "max_net_exposure": float(daily.get("net_exposure", pd.Series([0])).abs().max()),
        "max_long_exposure": float(daily.get("long_exposure", pd.Series([0])).max()),
        "max_short_exposure": float(daily.get("short_exposure", pd.Series([0])).max()),
        "both_long_short_days": int((daily.get("both_long_short_symbols", pd.Series([0])) > 0).sum()),
        "max_both_long_short_symbols": int(daily.get("both_long_short_symbols", pd.Series([0])).max()),
        "trades": len(trades),
        "symbol_concentration": _concentration(trades, "requested_symbol"),
        "strategy_concentration": _concentration(trades, "strategy"),
    }


def build_report(db_path: Path, start: str, end: str, cost_factor: float) -> dict[str, Any]:
    symbol_rows = {symbol: _run_symbol(db_path, symbol, start, end, cost_factor) for symbol in DEFAULT_SYMBOLS}
    daily = _daily_portfolio(symbol_rows)
    trades = [trade for row in symbol_rows.values() for trade in row["trades"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": CANDIDATE_NAME,
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "cost_factor": cost_factor,
        "portfolio_risk": _risk_metrics(daily, trades),
        "symbols": {
            symbol: {
                "data_symbol": row["data_symbol"],
                "report": row["report"],
                "risk": _risk_metrics(_daily_portfolio({symbol: row}), row["trades"]),
            }
            for symbol, row in symbol_rows.items()
        },
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    risk = payload["portfolio_risk"]
    lines = [
        "# SimNow Precheck Risk Report",
        "",
        f"- candidate: `{payload['candidate']}`",
        f"- period: `{payload['start']} ~ {payload['end']}`",
        f"- cost_factor: `{payload['cost_factor']}`",
        "",
        "## Portfolio Risk",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| total_return | {_fmt_pct(risk['total_return_pct'])} |",
        f"| max_single_day_loss | {_fmt_pct(risk['max_single_day_loss_pct'])} ({risk['max_single_day_loss_date']}) |",
        f"| max_single_day_gain | {_fmt_pct(risk['max_single_day_gain_pct'])} ({risk['max_single_day_gain_date']}) |",
        f"| max_drawdown | {_fmt_pct(risk['max_drawdown_pct'])} |",
        f"| max_recovery_days | {_fmt_num(risk['max_recovery_days'], 0)} |",
        f"| max_consecutive_loss_days | {_fmt_num(risk['max_consecutive_loss']['days'], 0)} |",
        f"| max_consecutive_loss_return | {_fmt_pct(risk['max_consecutive_loss']['cumulative_return_pct'])} |",
        f"| max_gross_exposure | {_fmt_pct(risk['max_gross_exposure'] * 100)} |",
        f"| max_net_exposure_abs | {_fmt_pct(risk['max_net_exposure'] * 100)} |",
        f"| max_long_exposure | {_fmt_pct(risk['max_long_exposure'] * 100)} |",
        f"| max_short_exposure | {_fmt_pct(risk['max_short_exposure'] * 100)} |",
        f"| both_long_short_days | {_fmt_num(risk['both_long_short_days'], 0)} |",
        f"| max_both_long_short_symbols | {_fmt_num(risk['max_both_long_short_symbols'], 0)} |",
        f"| trades | {_fmt_num(risk['trades'], 0)} |",
        "",
        "## Symbol Risk",
        "",
        "| symbol | return | max_day_loss | max_dd | max_gross | both_ls_days | trades |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, row in payload["symbols"].items():
        sr = row["risk"]
        lines.append(
            f"| {symbol} | {_fmt_pct(sr['total_return_pct'])} | {_fmt_pct(sr['max_single_day_loss_pct'])} | "
            f"{_fmt_pct(sr['max_drawdown_pct'])} | {_fmt_pct(sr['max_gross_exposure'] * 100)} | "
            f"{_fmt_num(sr['both_long_short_days'], 0)} | {_fmt_num(sr['trades'], 0)} |"
        )
    lines.extend([
        "",
        "## Symbol Concentration",
        "",
        f"- top1 abs share: `{risk['symbol_concentration']['top1_abs_share']:.2%}`",
        f"- top3 abs share: `{risk['symbol_concentration']['top3_abs_share']:.2%}`",
        "",
        "| symbol | weighted_pnl | abs_share |",
        "|---|---:|---:|",
    ])
    for row in risk["symbol_concentration"]["rows"]:
        lines.append(f"| {row['name']} | {_fmt_pct(row['weighted_pnl_pct'])} | {row['abs_share']:.2%} |")
    lines.extend([
        "",
        "## Sub-Strategy Concentration",
        "",
        f"- top1 abs share: `{risk['strategy_concentration']['top1_abs_share']:.2%}`",
        f"- top3 abs share: `{risk['strategy_concentration']['top3_abs_share']:.2%}`",
        "",
        "| strategy | weighted_pnl | abs_share |",
        "|---|---:|---:|",
    ])
    for row in risk["strategy_concentration"]["rows"]:
        lines.append(f"| {row['name']} | {_fmt_pct(row['weighted_pnl_pct'])} | {row['abs_share']:.2%} |")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SimNow precheck risk metrics for the final candidate.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--start", default=FULL_START)
    parser.add_argument("--end", default=FULL_END)
    parser.add_argument("--cost-factor", type=float, default=1.0)
    parser.add_argument("--out-json", type=Path, default=HERE / "simnow_precheck_risk_report.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "simnow_precheck_risk_report.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, args.start, args.end, args.cost_factor)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

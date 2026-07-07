from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sqlite3
import sys
from datetime import datetime
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
from diagnostics.platform_final_candidate import final_candidate_params  # noqa: E402
from diagnostics.platform_final_robustness_check import BASE_ENGINE_COMMISSION_RATE, BASE_ENGINE_SLIPPAGE  # noqa: E402
from diagnostics.portfolio_goal_evaluator import _json_safe, _strategy_weight  # noqa: E402
from diagnostics.simnow_precheck_risk_report import _concentration, _drawdown_stats, _max_consecutive_losses  # noqa: E402


def _parse_day(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _db_table_ranges(db_path: Path, symbols: list[str]) -> dict[str, dict[str, Any]]:
    ranges: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(db_path) as conn:
        for symbol in symbols:
            table = f"{symbol.lower()}_1M_raw"
            try:
                min_dt, max_dt, rows = conn.execute(
                    f"SELECT MIN(datetime), MAX(datetime), COUNT(*) FROM {table}"
                ).fetchone()
                ranges[symbol] = {
                    "table": table,
                    "min_datetime": min_dt,
                    "max_datetime": max_dt,
                    "rows": rows,
                }
            except Exception as exc:
                ranges[symbol] = {
                    "table": table,
                    "error": str(exc),
                }
    return ranges


def _latest_db_date(table_ranges: dict[str, dict[str, Any]]) -> str:
    max_values = [
        str(row.get("max_datetime", ""))[:10]
        for row in table_ranges.values()
        if row.get("max_datetime")
    ]
    return max(max_values) if max_values else ""


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
            engine.run()
        return {
            "symbol": symbol,
            "data_symbol": data_symbol,
            "engine": engine,
        }
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _events_for_day(row: dict[str, Any], day: datetime.date) -> dict[str, list[dict[str, Any]]]:
    engine = row["engine"]
    symbol = row["symbol"]
    signals = []
    for item in engine.signal_history:
        dt = item["dt"]
        if dt.date() == day:
            signals.append({
                "dt": dt.isoformat(sep=" "),
                "symbol": symbol,
                "strategy": "signal_snapshot",
                "operate": "SIGNAL",
                "signal_count": len(item.get("signals", {})),
                "price": item.get("price"),
            })
    trades = []
    for trade in engine.strategy.get_combined_trades():
        open_dt = trade.get("open_dt")
        close_dt = trade.get("close_dt")
        if getattr(open_dt, "date", lambda: None)() == day:
            trades.append({
                "dt": open_dt.isoformat(sep=" "),
                "symbol": symbol,
                "strategy": str(trade.get("strategy")),
                "operate": "OPEN",
                "price": trade.get("open_price"),
                "reason": trade.get("reason", ""),
                "pnl_pct": trade.get("pnl_pct"),
            })
        if getattr(close_dt, "date", lambda: None)() == day:
            trades.append({
                "dt": close_dt.isoformat(sep=" "),
                "symbol": symbol,
                "strategy": str(trade.get("strategy")),
                "operate": "CLOSE",
                "price": trade.get("close_price"),
                "reason": trade.get("reason", ""),
                "reason_code": trade.get("reason_code"),
                "pnl_pct": trade.get("pnl_pct"),
            })
    positions = []
    for item in engine.equity_curve:
        dt = item["dt"]
        if dt.date() == day:
            positions.append({
                "dt": dt.isoformat(sep=" "),
                "symbol": symbol,
                "strategy": "portfolio",
                "operate": "POSITION",
                "long_exposure": item.get("long_exposure", 0.0),
                "short_exposure": item.get("short_exposure", 0.0),
                "net_exposure": item.get("net_exposure", 0.0),
                "gross_exposure": item.get("gross_exposure", 0.0),
                "both_long_short": item.get("both_long_short", False),
                "equity": item.get("equity"),
            })
    return {"signals": signals, "trades": trades, "positions": positions}


def _portfolio_daily(rows: list[dict[str, Any]]) -> pd.DataFrame:
    curves = []
    exposures = []
    for row in rows:
        symbol = row["symbol"]
        eq = pd.DataFrame(row["engine"].equity_curve)
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
            out[col] = sum(exp_df[(row["symbol"], col)] for row in rows if (row["symbol"], col) in exp_df.columns) / len(rows)
        out["net_exposure"] = sum(exp_df[(row["symbol"], "net_exposure")] for row in rows if (row["symbol"], "net_exposure") in exp_df.columns) / len(rows)
        both_cols = [(row["symbol"], "both_long_short") for row in rows if (row["symbol"], "both_long_short") in exp_df.columns]
        out["both_long_short_symbols"] = exp_df[both_cols].sum(axis=1) if both_cols else 0
    return out


def _risk_for_day(daily: pd.DataFrame, trades: list[dict[str, Any]], day: datetime.date) -> dict[str, Any]:
    if daily.empty or day not in daily.index:
        return {}
    day_row = daily.loc[day]
    upto = daily.loc[:day]
    drawdown = _drawdown_stats(upto)
    return {
        "daily_return_pct": float(day_row["daily_return"]) * 100,
        "drawdown_pct": drawdown["max_drawdown_pct"],
        "gross_exposure": float(day_row.get("gross_exposure", 0.0)),
        "net_exposure": float(day_row.get("net_exposure", 0.0)),
        "long_exposure": float(day_row.get("long_exposure", 0.0)),
        "short_exposure": float(day_row.get("short_exposure", 0.0)),
        "both_long_short_symbols": int(day_row.get("both_long_short_symbols", 0)),
        "consecutive_loss": _max_consecutive_losses(upto),
        "symbol_concentration": _concentration(trades, "symbol"),
        "strategy_concentration": _concentration(trades, "strategy"),
    }


def build_snapshot(db_path: Path, start: str, end: str, day: str, cost_factor: float) -> dict[str, Any]:
    day_obj = _parse_day(day)
    day_text = day_obj.isoformat()
    table_ranges = _db_table_ranges(db_path, DEFAULT_SYMBOLS)
    latest_db_date = _latest_db_date(table_ranges)
    rows = [_run_symbol(db_path, symbol, start, end, cost_factor) for symbol in DEFAULT_SYMBOLS]
    events = {"signals": [], "trades": [], "positions": []}
    for row in rows:
        day_events = _events_for_day(row, day_obj)
        for key in events:
            events[key].extend(day_events[key])
    daily = _portfolio_daily(rows)
    closed_trades = []
    for row in rows:
        for trade in row["engine"].strategy.get_combined_trades():
            item = dict(trade)
            item["symbol"] = row["symbol"]
            item["weighted_pnl_pct"] = (
                float(item.get("pnl_pct", 0.0)) * _strategy_weight(str(item.get("strategy")), row["symbol"]) * 100 / len(DEFAULT_SYMBOLS)
            )
            closed_trades.append(item)
    risk = _risk_for_day(daily, closed_trades, day_obj)
    replay_available = bool(events["positions"]) and bool(risk)
    unavailable_reason = ""
    if not replay_available:
        # Only label the day as "no replay events" when every required symbol
        # already reaches the target date in the database. Otherwise it is a
        # historical data lag, even if some symbols have rows beyond ``day``.
        covers_day = all(
            bool(row.get("max_datetime")) and str(row["max_datetime"])[:10] >= day_text
            for row in table_ranges.values()
        )
        unavailable_reason = "historical_db_lag" if not covers_day else "no_replay_events_for_day"
    return {
        **events,
        "risk": risk,
        "meta": {
            "date": day,
            "start": start,
            "end": end,
            "db_path": str(db_path),
            "cost_factor": cost_factor,
            "replay_available": replay_available,
            "replay_unavailable_reason": unavailable_reason,
            "latest_db_date": latest_db_date,
            "table_ranges": table_ranges,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a replay snapshot matching the SimNow daily monitor schema.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", required=True, help="Replay end date, normally the trading day under review.")
    parser.add_argument("--date", required=True, help="Trading day to export, YYYY-MM-DD.")
    parser.add_argument("--cost-factor", type=float, default=1.0)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    payload = build_snapshot(args.db_path, args.start, args.end, args.date, args.cost_factor)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out_json}")


if __name__ == "__main__":
    main()

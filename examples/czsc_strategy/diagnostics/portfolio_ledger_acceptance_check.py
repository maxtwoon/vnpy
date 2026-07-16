"""A84 — Independent acceptance checks for the portfolio ledger report.

Re-runs each symbol through its own :class:`BacktestEngine` with
``sizing_model="risk"`` (the same settings the ledger report uses), rebuilds
a portfolio ledger from those independent per-symbol results, and compares it
to the ledger report produced by ``portfolio_ledger_report.py``.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.portfolio_ledger_report import (  # noqa: E402
    DEFAULT_END,
    DEFAULT_START,
    DEFAULT_SYMBOLS,
    _build_ledger,
    _infer_table_names,
    _json_safe,
    _risk_sizing_config,
    _symbol_clusters,
)


def _to_native(value: Any) -> Any:
    """Recursively convert numpy/pandas scalar types to plain Python types."""
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _run_independent_symbol(symbol: str, table_name: str | None) -> dict[str, Any]:
    """Run a single-symbol BacktestEngine with sizing_model='risk'."""
    engine = BacktestEngine(
        symbol=symbol,
        freq="1",
        start_date=DEFAULT_START,
        end_date=DEFAULT_END,
        initial_capital=BACKTEST_CONFIG["initial_capital"],
        commission_rate=BACKTEST_CONFIG["commission_rate"],
        slippage=BACKTEST_CONFIG["slippage"],
        db_path=SQLITE_DB_PATH,
        table_name=table_name,
        enable_short=STRATEGY_CONFIG.get("enable_short"),
    )
    with _risk_sizing_config():
        report = engine.run()
    if "error" in report:
        return {"engine": engine, "report": report, "error": report["error"]}
    return {"engine": engine, "report": report}


def _load_latest_ledger_payload() -> dict[str, Any]:
    """Load the most recent portfolio ledger JSON written by the report script."""
    out_dir = Path(__file__).resolve().parent
    json_files = sorted(out_dir.glob("portfolio_ledger_report_*.json"))
    if not json_files:
        raise FileNotFoundError("No portfolio_ledger_report_*.json found")
    with json_files[-1].open(encoding="utf-8") as f:
        return json.load(f)


def _compare_per_symbol_metrics(
    original: dict[str, Any], rebuilt: dict[str, Any]
) -> dict[str, Any]:
    """Compare per-symbol PnL/margin/trade-count between two payloads."""
    checks: dict[str, Any] = {}
    all_ok = True
    for symbol in original["symbols"]:
        orig = original["per_symbol"][symbol]
        new = rebuilt["per_symbol"][symbol]
        ok = (
            math.isclose(
                orig["total_realized_pnl_currency"],
                new["total_realized_pnl_currency"],
                rel_tol=1e-9,
            )
            and math.isclose(
                orig["max_total_open_margin"], new["max_total_open_margin"], rel_tol=1e-9
            )
            and math.isclose(
                orig["final_total_open_margin"],
                new["final_total_open_margin"],
                rel_tol=1e-9,
            )
            and orig["trade_count"] == new["trade_count"]
        )
        checks[f"per_symbol_{symbol}_metrics_match"] = ok
        all_ok = all_ok and ok
    checks["all_per_symbol_metrics_match"] = all_ok
    return checks


def _compare_summary_metrics(
    original: dict[str, Any], rebuilt: dict[str, Any]
) -> dict[str, Any]:
    """Compare portfolio-level summary numbers."""
    orig_summary = original["portfolio_summary"]
    new_summary = rebuilt["portfolio_summary"]
    return {
        "total_pnl_match": math.isclose(
            orig_summary["total_realized_pnl_currency"],
            new_summary["total_realized_pnl_currency"],
            rel_tol=1e-9,
        ),
        "max_total_open_margin_match": math.isclose(
            orig_summary["max_total_open_margin"],
            new_summary["max_total_open_margin"],
            rel_tol=1e-9,
        ),
        "final_total_open_margin_match": math.isclose(
            orig_summary["final_total_open_margin"],
            new_summary["final_total_open_margin"],
            rel_tol=1e-9,
        ),
        "max_margin_utilization_pct_match": math.isclose(
            orig_summary["max_margin_utilization_pct"],
            new_summary["max_margin_utilization_pct"],
            rel_tol=1e-9,
        ),
        "ledger_length_match": len(original["ledger"]) == len(rebuilt["ledger"]),
    }


def _rowwise_margin_check(
    original: dict[str, Any], rebuilt: dict[str, Any]
) -> dict[str, Any]:
    """Check that the timestamp-level portfolio margin series is identical."""
    orig_df = pd.DataFrame(original["ledger"]).rename(
        columns={"total_open_margin": "orig_total"}
    )
    reb_df = pd.DataFrame(rebuilt["ledger"]).rename(
        columns={"total_open_margin": "reb_total"}
    )
    merged = pd.merge(orig_df, reb_df, on="dt", how="outer")
    diff = (merged["orig_total"] - merged["reb_total"]).abs().max()
    return {
        "rowwise_max_abs_diff": float(diff),
        "rowwise_equal": bool(diff <= 1e-6),
    }


def _timestamp_level_symbol_checks(
    symbol_results: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Rebuild the per-symbol margin DataFrame and verify alignment/range rules."""
    margin_series: dict[str, pd.Series] = {}
    symbol_ranges: dict[str, tuple[Any, Any]] = {}

    for symbol, sr in symbol_results.items():
        if "error" in sr.get("report", {}):
            continue
        curve = sr["engine"].equity_curve
        if not curve:
            continue
        s = pd.Series(
            [float(e["total_open_margin"]) for e in curve],
            index=[e["dt"] for e in curve],
            name=symbol,
        )
        margin_series[symbol] = s
        symbol_ranges[symbol] = (s.index[0], s.index[-1])

    if not margin_series:
        return {"error": "no valid per-symbol margin series"}

    df = pd.concat(margin_series.values(), axis=1).sort_index().ffill()
    mask = pd.DataFrame(False, index=df.index, columns=df.columns)
    for symbol, (first_dt, last_dt) in symbol_ranges.items():
        mask[symbol] = (df.index >= first_dt) & (df.index <= last_dt)
    df = df.where(mask, 0.0).fillna(0.0)
    portfolio_margin = df.sum(axis=1)

    max_dt = portfolio_margin.idxmax()
    max_total = portfolio_margin.max()
    contributors = {
        symbol: float(df.loc[max_dt, symbol])
        for symbol in df.columns
        if float(df.loc[max_dt, symbol]) != 0.0
    }

    zero_outside_ok = True
    range_details: dict[str, Any] = {}
    for symbol, (first_dt, last_dt) in symbol_ranges.items():
        before = df.loc[df.index < first_dt, symbol]
        after = df.loc[df.index > last_dt, symbol]
        before_ok = before.abs().max() == 0.0 if not before.empty else True
        after_ok = after.abs().max() == 0.0 if not after.empty else True
        symbol_ok = before_ok and after_ok
        range_details[symbol] = {
            "first_dt": first_dt.isoformat(sep=" "),
            "last_dt": last_dt.isoformat(sep=" "),
            "zero_before_first": bool(before_ok),
            "zero_after_last": bool(after_ok),
            "overall_ok": bool(symbol_ok),
        }
        zero_outside_ok = zero_outside_ok and symbol_ok

    return {
        "max_margin_timestamp": max_dt.isoformat(sep=" "),
        "max_margin_value": float(max_total),
        "max_margin_contributors": contributors,
        "margin_zero_outside_range": zero_outside_ok,
        "margin_range_details": range_details,
    }


def _cluster_case_check(clusters: dict[str, list[str]]) -> dict[str, Any]:
    """Confirm cluster membership is case-insensitive for the real symbol list."""
    lower_symbols = [s.lower() for s in DEFAULT_SYMBOLS]
    orig_map = _symbol_clusters(clusters, DEFAULT_SYMBOLS)
    lower_map = _symbol_clusters(clusters, lower_symbols)
    ok = all(
        set(orig_map[s]) == set(lower_map[s.lower()]) for s in DEFAULT_SYMBOLS
    )
    return {
        "cluster_membership_case_insensitive": ok,
        "uppercase_mapping": orig_map,
        "lowercase_mapping": lower_map,
    }


def _cluster_metrics_check(
    original: dict[str, Any], rebuilt: dict[str, Any]
) -> dict[str, Any]:
    """Compare per-cluster max/final margins and symbol lists."""
    checks: dict[str, Any] = {}
    all_ok = True
    for cluster_name in set(original["per_cluster"]) | set(rebuilt["per_cluster"]):
        orig_c = original["per_cluster"].get(cluster_name, {})
        new_c = rebuilt["per_cluster"].get(cluster_name, {})
        ok = (
            set(orig_c.get("symbols", [])) == set(new_c.get("symbols", []))
            and math.isclose(
                orig_c.get("max_total_open_margin", 0.0),
                new_c.get("max_total_open_margin", 0.0),
                rel_tol=1e-9,
            )
            and math.isclose(
                orig_c.get("final_total_open_margin", 0.0),
                new_c.get("final_total_open_margin", 0.0),
                rel_tol=1e-9,
            )
        )
        checks[f"cluster_{cluster_name}_match"] = ok
        all_ok = all_ok and ok
    checks["all_cluster_metrics_match"] = all_ok
    return checks


def main() -> dict[str, Any]:
    """Run all acceptance checks and write the result JSON."""
    original = _load_latest_ledger_payload()
    table_names = _infer_table_names(DEFAULT_SYMBOLS, "1", str(SQLITE_DB_PATH))

    symbol_results: dict[str, dict[str, Any]] = {}
    for symbol in DEFAULT_SYMBOLS:
        symbol_results[symbol] = _run_independent_symbol(
            symbol, table_names.get(symbol)
        )

    initial_capital = float(BACKTEST_CONFIG["initial_capital"])
    corr_clusters = dict(STRATEGY_CONFIG.get("corr_clusters") or {})
    rebuilt = _build_ledger(symbol_results, initial_capital, corr_clusters)

    checks: dict[str, Any] = {}
    checks.update(_compare_per_symbol_metrics(original, rebuilt))
    checks.update(_compare_summary_metrics(original, rebuilt))
    checks.update(_rowwise_margin_check(original, rebuilt))
    checks.update(_timestamp_level_symbol_checks(symbol_results))
    checks.update(_cluster_case_check(corr_clusters))
    checks.update(_cluster_metrics_check(original, rebuilt))

    checks["overall_accepted"] = all(
        v for k, v in checks.items() if k.endswith("_match") or k.endswith("_equal") or k.endswith("_insensitive") or k.endswith("_range")
    )

    out_path = Path(__file__).resolve().parent / "portfolio_ledger_acceptance_check.json"
    native_checks = _to_native(checks)
    out_path.write_text(
        json.dumps(_json_safe(native_checks), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(_json_safe(native_checks), ensure_ascii=False, indent=2))
    return native_checks


if __name__ == "__main__":
    main()

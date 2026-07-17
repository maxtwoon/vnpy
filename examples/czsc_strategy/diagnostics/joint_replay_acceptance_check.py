"""A88 — Joint-clock replay real-data acceptance / sanity-check.

Runs :class:`PortfolioEngine` with ``sizing_model="risk"`` +
``portfolio_risk="on"`` (the A87 joint-clock replay with the shared
:class:`PortfolioLedger`) against the real historical SQLite DB for the same
5 symbols and window A83/A84 already validated
(``AP888``/``RB888``/``SC888``/``A888``/``ZN888``, 2022-01-01 ~ 2026-04-24),
then performs independent sanity checks on the joint report:

1. No crash / no data errors across all 5 symbols (``symbol_errors`` empty).
2. Equity/margin arithmetic sanity on the joint ``equity_curve``
   (``equity > 0``, ``total_open_margin >= 0``, ``margin_utilization_pct``
   finite, non-negative and not wildly discontinuous).
3. ``blocked_opens`` coherence: each entry's ``reason`` is one of
   ``"daily_loss_limit"``, ``"symbol_margin_cap"`` or
   ``"cluster_gross_cap:<name>"`` and its ``dt`` falls inside the run window.
   An empty list is a valid, reportable outcome (A84 recorded only ~6.49%
   peak margin utilization for this symbol set).
4. Comparison against A83/A84's independent-aggregation ledger: each symbol
   is re-run independently (same methodology as A84's acceptance check) and
   the joint replay's per-symbol trade sequences and total realized PnL are
   compared against it and against A83's recorded payload.
5. Case-insensitive cluster membership on real symbol names, plus a live
   :class:`PortfolioLedger` check that ``margin_by_cluster`` groups
   ``RB888``/``SC888``/``ZN888`` under ``industrial_energy``.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.portfolio_engine import PortfolioEngine  # noqa: E402
from chan_strategy.portfolio_ledger import PortfolioLedger  # noqa: E402
from diagnostics.portfolio_ledger_report import (  # noqa: E402
    DEFAULT_END,
    DEFAULT_START,
    DEFAULT_SYMBOLS,
    _infer_table_names,
    _json_safe,
    _run_per_symbol_engines,
    _symbol_clusters,
)

# Allowed blocked-open reason prefixes/names (from PortfolioLedger.pre_open_injection_for).
_FIXED_BLOCK_REASONS = {"daily_loss_limit", "symbol_margin_cap"}
_CLUSTER_BLOCK_PREFIX = "cluster_gross_cap:"

# "Reasonably close" tolerance for joint-vs-independent total realized PnL.
# Per-trade volumes are sized off the *shared* portfolio equity in the joint
# replay vs the *standalone* equity in A83/A84's independent runs; the two
# bases differ by the other symbols' cumulative PnL (A83/A84 recorded at most
# ~6.5% of initial capital for this symbol set), so per-trade lot counts can
# differ by that ratio plus integer-lot rounding. 0.20 is a generous bound.
_PNL_REL_TOL = 0.20


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


@contextmanager
def _joint_replay_config() -> Any:
    """Temporarily set ``sizing_model="risk"`` + ``portfolio_risk="on"`` and restore."""
    saved_sizing = STRATEGY_CONFIG.get("sizing_model")
    saved_risk = STRATEGY_CONFIG.get("portfolio_risk")
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["portfolio_risk"] = "on"
    try:
        yield
    finally:
        if saved_sizing is None:
            STRATEGY_CONFIG.pop("sizing_model", None)
        else:
            STRATEGY_CONFIG["sizing_model"] = saved_sizing
        if saved_risk is None:
            STRATEGY_CONFIG.pop("portfolio_risk", None)
        else:
            STRATEGY_CONFIG["portfolio_risk"] = saved_risk


def _run_joint_replay(table_names: dict[str, str]) -> dict[str, Any]:
    """Run the A87 joint-clock replay on the real DB (engine stdout silenced)."""
    engine = PortfolioEngine(
        symbols=list(DEFAULT_SYMBOLS),
        freq="1",
        start_date=DEFAULT_START,
        end_date=DEFAULT_END,
        initial_capital=BACKTEST_CONFIG["initial_capital"],
        commission_rate=BACKTEST_CONFIG["commission_rate"],
        slippage=BACKTEST_CONFIG["slippage"],
        db_path=str(SQLITE_DB_PATH),
        table_names=table_names,
        enable_short=STRATEGY_CONFIG.get("enable_short"),
    )
    with _joint_replay_config(), contextlib.redirect_stdout(io.StringIO()):
        report = engine.run()
    return report


def _run_independent() -> dict[str, dict[str, Any]]:
    """Re-run each symbol independently (same methodology as A84's check)."""
    return _run_per_symbol_engines(
        symbols=list(DEFAULT_SYMBOLS),
        freq="1",
        start_date=DEFAULT_START,
        end_date=DEFAULT_END,
        initial_capital=BACKTEST_CONFIG["initial_capital"],
        commission_rate=BACKTEST_CONFIG["commission_rate"],
        slippage=BACKTEST_CONFIG["slippage"],
        db_path=str(SQLITE_DB_PATH),
        table_names=None,
        enable_short=STRATEGY_CONFIG.get("enable_short"),
        quiet=True,
    )


def _load_a83_ledger_payload() -> dict[str, Any]:
    """Load the most recent A83 portfolio ledger JSON (independent aggregation)."""
    out_dir = Path(__file__).resolve().parent
    json_files = sorted(out_dir.glob("portfolio_ledger_report_*.json"))
    if not json_files:
        raise FileNotFoundError("No portfolio_ledger_report_*.json found")
    with json_files[-1].open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------- checks
def _check_symbol_errors(report: dict[str, Any]) -> dict[str, Any]:
    """1. No crash / no data errors across all symbols."""
    symbol_errors = report.get("symbol_errors", {})
    report_errors = {
        s: r.get("error") for s, r in (report.get("symbol_reports") or {}).items()
        if isinstance(r, dict) and "error" in r
    }
    return {
        "symbol_errors": dict(symbol_errors),
        "symbol_report_errors": report_errors,
        "no_symbol_errors": not symbol_errors and not report_errors,
        "symbols_run": list(report.get("symbols", [])),
    }


def _check_equity_margin_arithmetic(report: dict[str, Any]) -> dict[str, Any]:
    """2. Equity/margin arithmetic sanity on the joint equity curve."""
    curve = report.get("equity_curve", [])
    equities = [float(e["equity"]) for e in curve]
    margins = [float(e["total_open_margin"]) for e in curve]
    utils = [float(e["margin_utilization_pct"]) for e in curve]
    util_jumps = [abs(utils[i + 1] - utils[i]) for i in range(len(utils) - 1)]
    all_finite = all(
        math.isfinite(v) for series in (equities, margins, utils) for v in series
    )
    max_jump = max(util_jumps) if util_jumps else 0.0
    return {
        "curve_rows": len(curve),
        "first_dt": curve[0]["dt"].isoformat(sep=" ") if curve else None,
        "last_dt": curve[-1]["dt"].isoformat(sep=" ") if curve else None,
        "min_equity": min(equities) if equities else None,
        "max_equity": max(equities) if equities else None,
        "final_equity": equities[-1] if equities else None,
        "equity_always_positive": bool(equities) and all(e > 0 for e in equities),
        "margin_always_nonnegative": all(m >= 0 for m in margins),
        "max_total_open_margin": max(margins) if margins else None,
        "final_total_open_margin": margins[-1] if margins else None,
        "max_margin_utilization_pct": max(utils) if utils else None,
        "max_utilization_jump": max_jump,
        "utilization_in_range": all(0.0 <= u <= 1.0 for u in utils),
        "utilization_not_wildly_discontinuous": max_jump <= 0.25,
        "all_values_finite": all_finite,
    }


def _check_blocked_opens(report: dict[str, Any], corr_clusters: dict[str, list[str]]) -> dict[str, Any]:
    """3. blocked_opens coherence (empty is a valid, reportable outcome)."""
    blocked = report.get("blocked_opens", []) or []
    by_reason: dict[str, int] = {}
    by_symbol: dict[str, int] = {}
    by_date: dict[str, int] = {}
    entries_valid = True
    for entry in blocked:
        reason = str(entry.get("reason", ""))
        by_reason[reason] = by_reason.get(reason, 0) + 1
        symbol = str(entry.get("symbol", ""))
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        dt_date_key = str(entry.get("dt", ""))[:10]
        by_date[dt_date_key] = by_date.get(dt_date_key, 0) + 1
        reason_ok = (
            reason in _FIXED_BLOCK_REASONS
            or (
                reason.startswith(_CLUSTER_BLOCK_PREFIX)
                and reason[len(_CLUSTER_BLOCK_PREFIX):] in corr_clusters
            )
        )
        dt_str = str(entry.get("dt", ""))
        dt_date = dt_str[:10]
        window_ok = DEFAULT_START <= dt_date <= DEFAULT_END
        if not (reason_ok and window_ok):
            entries_valid = False
    return {
        "blocked_opens_count": len(blocked),
        "blocked_opens_by_reason": by_reason,
        "blocked_opens_by_symbol": by_symbol,
        "blocked_opens_by_date": by_date,
        "blocked_opens_coherent": entries_valid,
        "blocked_opens_sample": blocked[:5],
        "blocked_opens_full": blocked,
    }


def _check_clusters(corr_clusters: dict[str, list[str]]) -> dict[str, Any]:
    """5. Case-insensitive cluster membership + live margin_by_cluster grouping."""
    lower_symbols = [s.lower() for s in DEFAULT_SYMBOLS]
    orig_map = _symbol_clusters(corr_clusters, DEFAULT_SYMBOLS)
    lower_map = _symbol_clusters(corr_clusters, lower_symbols)
    case_insensitive = all(
        set(orig_map[s]) == set(lower_map[s.lower()]) for s in DEFAULT_SYMBOLS
    )

    # Live check: a PortfolioLedger fed 1.0 margin per symbol must group
    # RB888/SC888/ZN888 under industrial_energy.
    ledger = PortfolioLedger(
        list(DEFAULT_SYMBOLS),
        float(BACKTEST_CONFIG["initial_capital"]),
        dict(corr_clusters),
    )
    for symbol in DEFAULT_SYMBOLS:
        ledger.update_symbol_margin(symbol, 1.0)
    expected_cluster_margin = float(len(corr_clusters.get("industrial_energy", [])))
    live_grouping_ok = (
        ledger.margin_by_cluster.get("industrial_energy") == expected_cluster_margin
    )
    return {
        "cluster_membership_case_insensitive": case_insensitive,
        "uppercase_mapping": orig_map,
        "live_margin_by_cluster": dict(ledger.margin_by_cluster),
        "live_cluster_grouping_ok": live_grouping_ok,
    }


def _pair_timing_key(pair: dict[str, Any]) -> tuple:
    """Timing/price identity of a trade pair (excludes volume-derived fields)."""
    return (
        str(pair.get("strategy")),
        str(pair.get("open_dt")),
        str(pair.get("close_dt")),
        float(pair.get("open_price", 0.0)),
        float(pair.get("close_price", 0.0)),
    )


def _compare_symbol_trades(
    symbol: str,
    joint_pairs: list[dict[str, Any]],
    indep_pairs: list[dict[str, Any]],
    symbol_blocked: bool,
) -> dict[str, Any]:
    """Compare one symbol's joint trade sequence against its independent run."""
    joint_sorted = sorted(joint_pairs, key=lambda p: (p["open_dt"], p.get("strategy", "")))
    indep_sorted = sorted(indep_pairs, key=lambda p: (p["open_dt"], p.get("strategy", "")))

    joint_pnl = sum(float(p.get("pnl_currency", 0.0)) for p in joint_sorted)
    indep_pnl = sum(float(p.get("pnl_currency", 0.0)) for p in indep_sorted)

    count_equal = len(joint_sorted) == len(indep_sorted)
    timing_mismatches: list[dict[str, Any]] = []
    volume_diffs = 0
    if count_equal:
        for idx, (jp, ip) in enumerate(zip(joint_sorted, indep_sorted, strict=True)):
            if _pair_timing_key(jp) != _pair_timing_key(ip):
                if len(timing_mismatches) < 5:
                    timing_mismatches.append({
                        "index": idx,
                        "joint": _pair_timing_key(jp),
                        "independent": _pair_timing_key(ip),
                    })
            if int(jp.get("volume", 0)) != int(ip.get("volume", 0)):
                volume_diffs += 1

    timing_identical = count_equal and not timing_mismatches
    if not count_equal:
        classification = "diverged_trade_count"
    elif timing_mismatches:
        classification = "diverged_timing"
    elif volume_diffs:
        classification = "timing_identical_volume_differs"
    else:
        classification = "identical"

    # If nothing ever blocked this symbol, its trade sequence must not
    # diverge in count/timing (volume differences from shared-equity sizing
    # are an intended consequence of portfolio-level risk sizing, not gating).
    coherent = symbol_blocked or timing_identical

    return {
        "joint_trade_count": len(joint_sorted),
        "independent_trade_count": len(indep_sorted),
        "count_equal": count_equal,
        "timing_identical": timing_identical,
        "volume_diffs": volume_diffs,
        "classification": classification,
        "had_blocked_opens": symbol_blocked,
        "divergence_coherent": coherent,
        "timing_mismatch_sample": timing_mismatches,
        "joint_realized_pnl": joint_pnl,
        "independent_realized_pnl": indep_pnl,
    }


def _compare_with_independent(
    joint_report: dict[str, Any],
    independent: dict[str, dict[str, Any]],
    a83_payload: dict[str, Any],
) -> dict[str, Any]:
    """4. Compare the joint replay against A83/A84's independent aggregation."""
    joint_pairs = joint_report.get("pairs", []) or []
    blocked = joint_report.get("blocked_opens", []) or []
    blocked_symbols = {str(b.get("symbol")) for b in blocked}

    per_symbol: dict[str, Any] = {}
    for symbol in joint_report.get("symbols", []):
        sr = independent.get(symbol, {})
        engine = sr.get("engine")
        if engine is None or "error" in sr.get("report", {}):
            per_symbol[symbol] = {
                "error": sr.get("report", {}).get("error", "independent run missing")
            }
            continue
        joint_symbol_pairs = [p for p in joint_pairs if p.get("symbol") == symbol]
        indep_pairs = engine.strategy.get_combined_trades()
        per_symbol[symbol] = _compare_symbol_trades(
            symbol, joint_symbol_pairs, indep_pairs, symbol in blocked_symbols
        )

    joint_total_pnl = sum(float(p.get("pnl_currency", 0.0)) for p in joint_pairs)
    indep_total_pnl = sum(
        ps["independent_realized_pnl"]
        for ps in per_symbol.values()
        if "independent_realized_pnl" in ps
    )
    a83_total_pnl = float(
        a83_payload.get("portfolio_summary", {}).get("total_realized_pnl_currency", float("nan"))
    )

    abs_diff = abs(joint_total_pnl - indep_total_pnl)
    rel_diff = abs_diff / max(abs(indep_total_pnl), 1.0)
    unblocked = [s for s, ps in per_symbol.items() if not ps.get("had_blocked_opens", True)]

    return {
        "per_symbol": per_symbol,
        "joint_total_realized_pnl": joint_total_pnl,
        "independent_total_realized_pnl": indep_total_pnl,
        "a83_recorded_total_realized_pnl": a83_total_pnl,
        "joint_vs_independent_abs_diff": abs_diff,
        "joint_vs_independent_rel_diff": rel_diff,
        "pnl_reasonably_close": rel_diff <= _PNL_REL_TOL,
        "unblocked_symbols_timing_identical": all(
            per_symbol[s].get("timing_identical", False) for s in unblocked
        ),
        "all_divergences_coherent": all(
            ps.get("divergence_coherent", False) for ps in per_symbol.values()
        ),
    }


def main() -> dict[str, Any]:
    """Run the joint replay + all acceptance checks and write the result JSON."""
    corr_clusters = dict(STRATEGY_CONFIG.get("corr_clusters") or {})
    table_names = _infer_table_names(DEFAULT_SYMBOLS, "1", str(SQLITE_DB_PATH))
    print(f"[A88] inferred table names: {table_names}")

    print("[A88] running joint replay (sizing_model=risk, portfolio_risk=on) ...")
    joint_report = _run_joint_replay(table_names)
    print(
        f"[A88] joint replay done: symbols={joint_report.get('symbols')}, "
        f"curve_rows={len(joint_report.get('equity_curve', []))}, "
        f"pairs={len(joint_report.get('pairs', []))}, "
        f"blocked_opens={len(joint_report.get('blocked_opens', []) or [])}"
    )

    print("[A88] re-running independent per-symbol engines (A84 methodology) ...")
    independent = _run_independent()
    print("[A88] independent runs done")

    a83_payload = _load_a83_ledger_payload()

    checks: dict[str, Any] = {}
    checks["config"] = {
        "symbols": list(DEFAULT_SYMBOLS),
        "window": f"{DEFAULT_START} ~ {DEFAULT_END}",
        "db_path": str(SQLITE_DB_PATH),
        "initial_capital": float(BACKTEST_CONFIG["initial_capital"]),
        "sizing_model": "risk",
        "portfolio_risk": "on",
        "max_margin_pct": float(STRATEGY_CONFIG.get("max_margin_pct", 0.50)),
        "max_symbol_margin_pct": float(STRATEGY_CONFIG.get("max_symbol_margin_pct", 1.0)),
        "cluster_gross_cap": float(STRATEGY_CONFIG.get("cluster_gross_cap", 1.0)),
        "daily_loss_limit_pct": float(STRATEGY_CONFIG.get("daily_loss_limit_pct", 0.03)),
        "corr_clusters": {k: list(v) for k, v in corr_clusters.items()},
    }
    checks.update(_check_symbol_errors(joint_report))
    checks.update(_check_equity_margin_arithmetic(joint_report))
    checks.update(_check_blocked_opens(joint_report, corr_clusters))
    checks.update(_check_clusters(corr_clusters))
    checks["comparison_vs_independent"] = _compare_with_independent(
        joint_report, independent, a83_payload
    )
    checks["loss_limit_triggers"] = joint_report.get("loss_limit_triggers", [])
    checks["flatten_on_breach"] = joint_report.get("flatten_on_breach")

    checks["overall_accepted"] = all([
        checks["no_symbol_errors"],
        checks["equity_always_positive"],
        checks["margin_always_nonnegative"],
        checks["utilization_in_range"],
        checks["utilization_not_wildly_discontinuous"],
        checks["all_values_finite"],
        checks["blocked_opens_coherent"],
        checks["cluster_membership_case_insensitive"],
        checks["live_cluster_grouping_ok"],
        checks["comparison_vs_independent"]["pnl_reasonably_close"],
        checks["comparison_vs_independent"]["unblocked_symbols_timing_identical"],
        checks["comparison_vs_independent"]["all_divergences_coherent"],
    ])

    out_path = Path(__file__).resolve().parent / "joint_replay_acceptance_check.json"
    native_checks = _to_native(checks)
    out_path.write_text(
        json.dumps(_json_safe(native_checks), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(_json_safe(native_checks), ensure_ascii=False, indent=2))
    return native_checks


if __name__ == "__main__":
    main()

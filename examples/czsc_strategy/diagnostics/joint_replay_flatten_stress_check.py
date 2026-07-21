"""A92 — Forced-liquidation real-data stress check (tightened threshold).

Closes audit H3's real-data gap: A90's forced liquidation
(``PortfolioEngine._build_joint_report()``'s flatten driver) had only ever been
exercised by constructed unit-test fixtures — on the real 5-symbol acceptance
window (``AP888``/``RB888``/``SC888``/``A888``/``ZN888``,
2022-01-01 ~ 2026-04-24) the production default ``daily_loss_limit_pct=0.03``
triggers once (2022-03-30) at a moment when every symbol was already flat, so
``flat_events`` has never been non-empty on real data.

This diagnostic re-runs the SAME symbols / SAME window / SAME DB with a
deliberately tightened ``daily_loss_limit_pct`` (runtime override inside a
context manager — NO config default change, NO production-code change) chosen
so a trigger occurs while at least one symbol demonstrably holds an open
position, then independently verifies:

1. ``flat_events`` is non-empty — the mechanism really closed a real position.
2. No entry closes before it opened (``open_dt <= flat_dt``).  One legitimate
   edge case exists: the *triggering* symbol may open a position at the trigger
   bar's own ``pre_open`` (the limit is not yet active at that point) and be
   flattened at the SAME bar's close when the breach is detected post-bar —
   causally ordered within the bar (open at bar open, flatten at bar close),
   so ``open_dt == flat_dt`` is allowed only for immediate (triggering-symbol)
   events and is counted separately.
3. Every entry's ``flat_price`` equals that symbol's OWN trade-bar ``close``
   at the entry's own ``dt`` — verified against freshly re-loaded and
   re-resampled bar data (same DB, same ``resample_bars`` pipeline the engine
   itself uses), NOT against the report's own numbers.
4. Entries at a trigger tick (immediate flatten of the triggering symbol) use
   that symbol's own trigger-tick close; entries after the trigger tick
   (deferred, lagging symbols) use THEIR OWN tick's close — never the trigger
   tick's price (``docs/design/a89-forced-liquidation-design.md`` §3).

Usage::

    python diagnostics/joint_replay_flatten_stress_check.py [threshold]

``threshold`` defaults to :data:`DEFAULT_TIGHTENED_THRESHOLD` (see the A92
evidence artifact ``joint_replay_flatten_stress_2026-07-21.md`` for how it was
found).  This tightened value is for stress-testing ONLY — it is not the
production default and does not imply the real 0.03 default triggers this
often (A88 established it triggers once in ~4 years for this symbol set).

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.data_adapter import resample_bars  # noqa: E402
from chan_strategy.portfolio_engine import PortfolioEngine  # noqa: E402
from diagnostics.portfolio_ledger_report import (  # noqa: E402
    DEFAULT_END,
    DEFAULT_START,
    DEFAULT_SYMBOLS,
    _infer_table_names,
    _json_safe,
)

# Tightened stress threshold found by exploratory search (see the A92 evidence
# artifact).  Overridable via CLI argv[1].
DEFAULT_TIGHTENED_THRESHOLD = 0.005

# Float tolerance when comparing a flat_price against a re-loaded bar close.
_PRICE_ABS_TOL = 1e-6


@contextmanager
def _stress_config(daily_loss_limit_pct: float) -> Any:
    """Temporarily set the joint-replay keys + a tightened loss limit; restore after."""
    saved = {
        k: STRATEGY_CONFIG.get(k)
        for k in ("sizing_model", "portfolio_risk", "daily_loss_limit_pct")
    }
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["portfolio_risk"] = "on"
    STRATEGY_CONFIG["daily_loss_limit_pct"] = daily_loss_limit_pct
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                STRATEGY_CONFIG.pop(k, None)
            else:
                STRATEGY_CONFIG[k] = v


def _run_stress_replay(threshold: float, table_names: dict[str, str]) -> dict[str, Any]:
    """Run the joint replay once with the tightened threshold (stdout silenced)."""
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
    with _stress_config(threshold), contextlib.redirect_stdout(io.StringIO()):
        report = engine.run()
    return report


def _load_trade_bar_closes(symbol: str, table_name: str | None) -> dict[str, float]:
    """Independently re-load one symbol's trade bars and map ``dt -> close``.

    Uses the exact same data path as ``BacktestEngine.bar_generator()`` (same
    DB, same ``load_data()``, same ``resample_bars()`` with the same trade-freq
    config) but runs NO strategy logic, so the price lookup is independent of
    the report's own numbers.
    """
    engine = BacktestEngine(
        symbol=symbol,
        freq="1",
        start_date=DEFAULT_START,
        end_date=DEFAULT_END,
        initial_capital=BACKTEST_CONFIG["initial_capital"],
        commission_rate=BACKTEST_CONFIG["commission_rate"],
        slippage=BACKTEST_CONFIG["slippage"],
        db_path=str(SQLITE_DB_PATH),
        table_name=table_name,
        enable_short=STRATEGY_CONFIG.get("enable_short"),
    )
    if not engine.load_data():
        raise RuntimeError(f"bar reload failed for {symbol}")
    trade_freq_name = STRATEGY_CONFIG.get("trade_freq", "30分钟")
    trade_minutes = engine._freq_to_minutes(trade_freq_name)
    trade_freq_obj = engine._freq_name_to_czsc_freq(trade_freq_name)
    trade_bars = resample_bars(engine.bars, trade_freq_obj, trade_minutes)
    return {b.dt.isoformat(sep=" "): float(b.close) for b in trade_bars}


def _check_flat_events(
    report: dict[str, Any], closes_by_symbol: dict[str, dict[str, float]]
) -> dict[str, Any]:
    """Verify every flat event against independently re-loaded bar closes."""
    flat_events = report.get("flat_events", []) or []
    triggers = report.get("loss_limit_triggers", []) or []
    trigger_dts = sorted(str(t.get("dt", "")) for t in triggers)

    entries_valid = True
    classified: list[dict[str, Any]] = []
    for entry in flat_events:
        symbol = str(entry.get("symbol", ""))
        dt = str(entry.get("dt", ""))
        open_dt = str(entry.get("open_dt") or "")
        flat_price = float(entry.get("flat_price", float("nan")))

        # Most recent trigger at or before this event: if the event's dt IS a
        # trigger dt it is the immediate flatten of the triggering symbol;
        # otherwise it is a deferred (lagging-symbol) flatten at its own tick.
        prior_triggers = [t for t in trigger_dts if t <= dt]
        immediate = bool(prior_triggers) and prior_triggers[-1] == dt
        kind = "immediate" if immediate else "deferred"

        own_close = closes_by_symbol.get(symbol, {}).get(dt)
        price_matches_own_close = (
            own_close is not None and abs(flat_price - own_close) <= _PRICE_ABS_TOL
        )
        same_bar = bool(open_dt) and open_dt == dt
        open_not_after_flat = bool(open_dt) and open_dt <= dt
        # A same-bar open+flatten is only causally possible for the immediate
        # (triggering-symbol) flatten — a deferred flatten happens at the
        # symbol's own pre_open BEFORE any open at that tick (which is then
        # blocked by the saturated-margin injection anyway).
        entry_valid = (
            price_matches_own_close
            and open_not_after_flat
            and (not same_bar or immediate)
        )
        if not entry_valid:
            entries_valid = False
        classified.append({
            "dt": dt,
            "symbol": symbol,
            "strategy": entry.get("strategy"),
            "kind": kind,
            "open_dt": open_dt,
            "flat_price": flat_price,
            "own_bar_close_at_flat_dt": own_close,
            "price_matches_own_close": price_matches_own_close,
            "open_not_after_flat": open_not_after_flat,
            "same_bar_open_flatten": same_bar,
        })

    immediate_events = [e for e in classified if e["kind"] == "immediate"]
    deferred_events = [e for e in classified if e["kind"] == "deferred"]
    same_bar_events = [e for e in classified if e["same_bar_open_flatten"]]

    return {
        "flat_events_count": len(flat_events),
        "flat_events_non_empty": bool(flat_events),
        "all_open_dt_not_after_flat_dt": all(
            e["open_not_after_flat"] for e in classified
        ),
        "same_bar_open_flatten_count": len(same_bar_events),
        "same_bar_events_all_immediate": all(
            e["kind"] == "immediate" for e in same_bar_events
        ),
        "all_prices_match_own_bar_close": all(
            e["price_matches_own_close"] for e in classified
        ),
        "immediate_flat_events_count": len(immediate_events),
        "deferred_flat_events_count": len(deferred_events),
        # The deferred-flatten price invariant is only *provable* on real data
        # when at least one deferred event exists; report it explicitly.
        "deferred_invariant_exercised": bool(deferred_events),
        "flat_events_coherent": entries_valid,
        "classified_flat_events": classified,
    }


def main() -> dict[str, Any]:
    """Run the tightened-threshold stress replay and verify the flatten path."""
    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TIGHTENED_THRESHOLD
    table_names = _infer_table_names(DEFAULT_SYMBOLS, "1", str(SQLITE_DB_PATH))
    print(f"[A92] inferred table names: {table_names}")
    print(f"[A92] running stress joint replay (daily_loss_limit_pct={threshold}) ...")
    report = _run_stress_replay(threshold, table_names)
    triggers = report.get("loss_limit_triggers", []) or []
    flat_events = report.get("flat_events", []) or []
    print(
        f"[A92] stress replay done: triggers={len(triggers)}, "
        f"flat_events={len(flat_events)}, pairs={len(report.get('pairs', []))}"
    )

    # Independent price verification: re-load trade bars only for symbols that
    # actually appear in flat_events.
    involved_symbols = sorted({str(e.get("symbol")) for e in flat_events})
    closes_by_symbol: dict[str, dict[str, float]] = {}
    for symbol in involved_symbols:
        print(f"[A92] independently re-loading trade bars for {symbol} ...")
        with contextlib.redirect_stdout(io.StringIO()):
            closes_by_symbol[symbol] = _load_trade_bar_closes(
                symbol, table_names.get(symbol)
            )

    checks: dict[str, Any] = {}
    checks["config"] = {
        "symbols": list(DEFAULT_SYMBOLS),
        "window": f"{DEFAULT_START} ~ {DEFAULT_END}",
        "db_path": str(SQLITE_DB_PATH),
        "initial_capital": float(BACKTEST_CONFIG["initial_capital"]),
        "sizing_model": "risk",
        "portfolio_risk": "on",
        "daily_loss_limit_pct_stress": threshold,
        "daily_loss_limit_pct_production_default": float(
            STRATEGY_CONFIG.get("daily_loss_limit_pct", 0.03)
        ),
        "stress_threshold_is_temporary_override": True,
    }
    checks["symbol_errors"] = report.get("symbol_errors", {})
    checks["no_symbol_errors"] = not report.get("symbol_errors")
    checks["loss_limit_triggers"] = triggers
    checks["flatten_status"] = report.get("flatten_status")
    checks.update(_check_flat_events(report, closes_by_symbol))

    checks["overall_accepted"] = all([
        checks["no_symbol_errors"],
        checks["flat_events_non_empty"],
        checks["all_open_dt_not_after_flat_dt"],
        checks["same_bar_events_all_immediate"],
        checks["all_prices_match_own_bar_close"],
        checks["flat_events_coherent"],
    ])

    out_path = Path(__file__).resolve().parent / "joint_replay_flatten_stress_check.json"
    out_path.write_text(
        json.dumps(_json_safe(checks), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(_json_safe(checks), ensure_ascii=False, indent=2))
    return checks


if __name__ == "__main__":
    main()

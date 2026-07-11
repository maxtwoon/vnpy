"""A40 research-mode equivalence regression test.

Requires the local historical SQLite database.  Verifies that with
STRATEGY_CONFIG['sizing_model'] == 'research' the observable backtest output
(pnl_pct, open/close price, bars_held, reason, equity curve) is unchanged from
the stored baseline.  New additive fields (volume, pnl_currency) are allowed but
must take their research-mode default values.

RESEARCH-ONLY, not a trading recommendation.
"""
import json
from pathlib import Path

import pytest

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG


SYMBOLS = ["SC888", "RB888"]
START = "2023-01-01"
END = "2023-12-31"
SNAPSHOT_PATH = Path(__file__).with_name("test_position_sizing_research_equivalence.snapshot.json")


@pytest.fixture(autouse=True)
def restore_sizing_config():
    saved = STRATEGY_CONFIG.get("sizing_model", "research")
    yield
    STRATEGY_CONFIG["sizing_model"] = saved


def _run_symbol(symbol: str) -> dict:
    STRATEGY_CONFIG["sizing_model"] = "research"
    engine = BacktestEngine(
        symbol=symbol,
        freq="1",
        start_date=START,
        end_date=END,
        table_name=f"{symbol}_1M_raw",
    )
    report = engine.run()
    if "error" in report:
        pytest.skip(f"{symbol}: {report['error']}")

    pairs = engine.strategy.get_combined_trades()
    return {
        "symbol": symbol,
        "report": {
            k: v
            for k, v in report.items()
            if k not in ("sub_strategies",)
        },
        "pairs": [
            {
                "strategy": p.get("strategy"),
                "open_dt": _fmt_dt(p.get("open_dt")),
                "close_dt": _fmt_dt(p.get("close_dt")),
                "open_price": p.get("open_price"),
                "close_price": p.get("close_price"),
                "pnl_pct": p.get("pnl_pct"),
                "bars_held": p.get("bars_held"),
                "reason": p.get("reason"),
                "reason_code": p.get("reason_code"),
            }
            for p in pairs
        ],
        "equity_curve": [
            {
                "dt": _fmt_dt(e.get("dt")),
                "price": e.get("price"),
                "equity": e.get("equity"),
                "positions": e.get("positions"),
                "long_exposure": e.get("long_exposure"),
                "short_exposure": e.get("short_exposure"),
                "net_exposure": e.get("net_exposure"),
                "gross_exposure": e.get("gross_exposure"),
                "both_long_short": e.get("both_long_short"),
            }
            for e in engine.equity_curve
        ],
    }


def _fmt_dt(value):
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


@pytest.mark.realdb
@pytest.mark.slow
def test_research_mode_equivalence_to_baseline():
    """Research mode must reproduce the stored baseline (empty diff on observable fields)."""
    actual = {symbol: _run_symbol(symbol) for symbol in SYMBOLS}

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        pytest.skip(f"Baseline snapshot created at {SNAPSHOT_PATH}; re-run to compare.")

    baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert actual == baseline, "Research-mode output differs from stored baseline."


@pytest.mark.realdb
@pytest.mark.slow
def test_research_mode_additive_fields_take_default_values():
    """volume=1, multiplier=1, pnl_currency = pnl_pct * open_price in research mode."""
    for symbol in SYMBOLS:
        STRATEGY_CONFIG["sizing_model"] = "research"
        engine = BacktestEngine(
            symbol=symbol,
            freq="1",
            start_date=START,
            end_date=END,
            table_name=f"{symbol}_1M_raw",
        )
        report = engine.run()
        if "error" in report:
            pytest.skip(f"{symbol}: {report['error']}")
        for p in engine.strategy.get_combined_trades():
            assert p.get("volume", 1) == 1
            assert p.get("contract_multiplier", 1) == 1
            assert p.get("pnl_currency") == pytest.approx(p["pnl_pct"] * p["open_price"])

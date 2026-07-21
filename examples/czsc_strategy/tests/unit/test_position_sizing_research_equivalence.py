"""A40/A91 research-mode equivalence regression test.

Requires the local historical SQLite database.  Verifies that with
STRATEGY_CONFIG['sizing_model'] == 'research' the computed backtest output is
unchanged from the stored baseline.  What is compared (A91 whitelist-based):

* ``pairs``        — full equality (trade list: strategy, open/close dt & price,
                     pnl_pct, bars_held, reason, reason_code).
* ``equity_curve`` — full equality (per-bar price/equity/exposure fields).
* ``report``       — full equality on the Bucket-B whitelist
                     (``EQUIVALENCE_REPORT_FIELDS``) only, plus full
                     equality on ``sub_strategies`` (see below).

Bucket-A (config echo / label) report fields are deliberately NOT diffed
against the baseline: new keys may appear and existing ones may change when a
new opt-in feature is added, without breaking research-mode equivalence.  They
are instead shape-checked (presence + type) here and default-value-checked in
``test_research_mode_additive_fields_take_default_values``.

Key classification of ``BacktestEngine.generate_report()`` output
(cross-checked against backtest_engine.py on 2026-07-21):

* Bucket A — config echo / labels (value is a passthrough of STRATEGY_CONFIG
  or run metadata, not derived from what the strategy decided on the data):
  ``symbol``, ``freq``, ``sizing_model``, ``limit_halt_model``,
  ``exit_event_semantics``, ``stop_execution_model``, ``stop_penalty_bp``,
  ``resonance_filter``, ``portfolio_risk``, ``rollover_open_gating``,
  ``weighting``, ``period``, ``mode_label``, ``sizing_caveat``.
* Bucket B — computed strategy output (derived from the trade/equity sequence
  produced for this input data; a silent change here IS a regression):
  ``total_bars``, ``unparseable_rows_skipped``, ``traded_bars``,
  ``sub_strategies``, ``max_long_exposure``, ``max_short_exposure``,
  ``max_gross_exposure``, ``both_long_short_bars``, ``total_trades``,
  ``win_rate``, ``avg_profit_pct``, ``avg_loss_pct``, ``profit_factor``,
  ``max_profit_pct``, ``max_loss_pct``, ``avg_bars_held``, ``final_equity``,
  ``total_return_pct``, ``max_drawdown_pct``, ``sharpe_ratio``,
  plus conditional keys: ``max_total_open_margin``,
  ``max_margin_utilization_pct``, ``final_total_open_margin`` (risk sizing
  only) and ``rollover_open_gating_rejected_opens``,
  ``rollover_open_gating_unavailable`` (gating on only).
  ``sub_strategies`` is Bucket B and IS snapshotted and compared, but via
  a separate full-equality assertion rather than
  ``EQUIVALENCE_REPORT_FIELDS``: it is a nested dict
  ``{pos_name: {stat: value}}`` (per-sub-strategy ``Position.evaluate()``
  output, all numeric), not a flat scalar, so it does not fit the
  whitelist's flat ``.get(field)`` loop.  Comparing only portfolio-level
  aggregates would leave a gap — two different distributions of trades
  across sub-strategies could produce identical aggregates while differing
  at the sub-strategy level.  The conditional keys never appear under the
  research-default config this test runs, so they are not in the whitelist.

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

# Bucket B whitelist: flat scalar computed report fields diffed against the
# baseline.  ``sub_strategies`` is Bucket B too, but compared separately as a
# nested dict (see module docstring).
EQUIVALENCE_REPORT_FIELDS = (
    "total_bars",
    "unparseable_rows_skipped",
    "traded_bars",
    "max_long_exposure",
    "max_short_exposure",
    "max_gross_exposure",
    "both_long_short_bars",
    "total_trades",
    "win_rate",
    "avg_profit_pct",
    "avg_loss_pct",
    "profit_factor",
    "max_profit_pct",
    "max_loss_pct",
    "avg_bars_held",
    "final_equity",
    "total_return_pct",
    "max_drawdown_pct",
    "sharpe_ratio",
)

# Bucket A shape contract: presence + type, so a wholesale-missing config-echo
# key is still caught as a shape regression (values are free to change).
BUCKET_A_EXPECTED_TYPES = {
    "symbol": str,
    "freq": str,
    "sizing_model": str,
    "limit_halt_model": str,
    "exit_event_semantics": str,
    "stop_execution_model": str,
    "stop_penalty_bp": (int, float),
    "resonance_filter": str,
    "portfolio_risk": str,
    "rollover_open_gating": str,
    "weighting": str,
    "period": str,
    "mode_label": str,
    "sizing_caveat": (str, type(None)),
}


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
        # Full report dict, including sub_strategies (pure numeric nested
        # dict; no datetime formatting needed, unlike pairs/equity_curve).
        "report": dict(report),
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
    """Research mode must reproduce the stored baseline on computed output.

    Compares ``pairs`` and ``equity_curve`` by full equality, ``report``
    by full equality restricted to the Bucket-B whitelist
    (``EQUIVALENCE_REPORT_FIELDS``), and ``sub_strategies`` by full
    equality as a nested dict.  Bucket-A config-echo fields are
    shape-checked (presence + type) but never value-diffed against baseline.
    """
    actual = {symbol: _run_symbol(symbol) for symbol in SYMBOLS}

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        pytest.skip(f"Baseline snapshot created at {SNAPSHOT_PATH}; re-run to compare.")

    baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    for symbol in SYMBOLS:
        act = actual[symbol]
        base = baseline[symbol]

        assert act["pairs"] == base["pairs"], (
            f"{symbol}: trade pairs differ from stored baseline."
        )
        assert act["equity_curve"] == base["equity_curve"], (
            f"{symbol}: equity curve differs from stored baseline."
        )
        assert act["report"].get("sub_strategies") == base["report"].get("sub_strategies"), (
            f"{symbol}: sub_strategies (per-sub-strategy computed stats) "
            f"differ from stored baseline."
        )

        diffs = []
        for field in EQUIVALENCE_REPORT_FIELDS:
            missing = object()
            a_val = act["report"].get(field, missing)
            b_val = base["report"].get(field, missing)
            if a_val is missing:
                diffs.append(f"{field}: MISSING in current report")
            elif b_val is missing:
                diffs.append(f"{field}: MISSING in baseline report")
            elif a_val != b_val:
                diffs.append(f"{field}: baseline={b_val!r} actual={a_val!r}")
        assert not diffs, (
            f"{symbol}: computed (Bucket-B) report fields differ from baseline:\n  "
            + "\n  ".join(diffs)
        )

        for field, expected_type in BUCKET_A_EXPECTED_TYPES.items():
            assert field in act["report"], (
                f"{symbol}: config-echo field {field!r} missing from report "
                f"(shape regression)."
            )
            assert isinstance(act["report"][field], expected_type), (
                f"{symbol}: config-echo field {field!r} has unexpected type "
                f"{type(act['report'][field]).__name__} (expected {expected_type})."
            )


@pytest.mark.realdb
@pytest.mark.slow
def test_research_mode_additive_fields_take_default_values():
    """volume=1, multiplier=1, pnl_currency = pnl_pct * open_price in research mode.

    Also pins the Bucket-A config-echo fields to their expected research-mode
    defaults (pure-default config => mode_label == "RESEARCH_BASELINE").
    """
    expected_config_echo = {
        "sizing_model": "research",
        "limit_halt_model": "off",
        "resonance_filter": "off",
        "portfolio_risk": "off",
        "rollover_open_gating": "off",
        "mode_label": "RESEARCH_BASELINE",
    }
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

        for field, expected in expected_config_echo.items():
            assert report.get(field) == expected, (
                f"{symbol}: research-mode default for {field!r} is {expected!r}, "
                f"got {report.get(field)!r}."
            )
        assert isinstance(report.get("sizing_caveat"), str) and report["sizing_caveat"], (
            f"{symbol}: research mode must surface a non-empty sizing_caveat."
        )

        for p in engine.strategy.get_combined_trades():
            assert p.get("volume", 1) == 1
            assert p.get("contract_multiplier", 1) == 1
            assert p.get("pnl_currency") == pytest.approx(p["pnl_pct"] * p["open_price"])

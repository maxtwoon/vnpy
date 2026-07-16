"""A86 — BacktestEngine per-bar generator extraction unit tests.

Validates the nested-generator-closure refactor of ``BacktestEngine.run()``:

(a) fully draining ``bar_generator()`` with ``.send(None)`` throughout
    reproduces the exact same ``equity_curve``/report as calling ``run()``
    directly on the same engine config (default-drain byte-identity);
(b) sending a deliberately different ``(equity, total_open_margin)`` override
    at a ``pre_open`` yield changes the resulting ``Position._size_open()``
    lot sizing for that bar (the injection point reaches position sizing).

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from math import floor

import pytest

import chan_strategy.backtest_engine as be
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import Operate, _research_contract_spec

FREQ = "30分钟"

# Minimal signal set that satisfies the 一买多头 open Event (daily filter and
# ATR chop filter are disabled under the default config + mini fixture).
BUY1_SIGNALS = {
    f"{FREQ}_D1ZS_数据状态V260615": "充分_任意_任意_0",
    f"{FREQ}_D1ZS_结构状态V260615": "已确认_任意_任意_0",
    f"{FREQ}_D1BSP_一买V260615": "一买确认_任意_任意_0",
    f"{FREQ}_D1BI_方向V260615": "向上_任意_任意_0",
}


@pytest.fixture(autouse=True)
def restore_config():
    """Snapshot and restore the whole STRATEGY_CONFIG so tests never leak."""
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _make_engine(bars) -> BacktestEngine:
    engine = BacktestEngine("TEST", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    return engine


def _patch_buy1_signals(monkeypatch) -> None:
    """Force a 一买 open signal on the first signal call of each engine run.

    Every ``BacktestEngine`` run builds a fresh trade-frequency CZSC object, so
    keying on the object identity fires exactly once per run, no matter how
    many engines share the patch. Strong references avoid id() reuse.
    """
    seen: list = []

    def fake_get_all_signals(czsc_obj, freq, **kwargs):
        if freq == FREQ and not any(czsc_obj is o for o in seen):
            seen.append(czsc_obj)
            return dict(BUY1_SIGNALS)
        return {}

    monkeypatch.setattr(be, "get_all_signals", fake_get_all_signals)


def _drain(gen, pre_open_overrides: dict | None = None):
    """Drive a bar generator to exhaustion.

    :param pre_open_overrides: {dt: (equity, total_open_margin)} sent back at
        the matching "pre_open" yield; every other yield gets None.
    :return: (list of yielded items, report from StopIteration.value)
    """
    pre_open_overrides = pre_open_overrides or {}
    yielded = []
    to_send = None
    try:
        while True:
            item = gen.send(to_send)
            to_send = None
            yielded.append(item)
            kind, dt, _price, _eq, _margin = item
            if kind == "pre_open" and dt in pre_open_overrides:
                to_send = pre_open_overrides[dt]
    except StopIteration as stop:
        return yielded, stop.value


def _first_long_open(engine: BacktestEngine):
    """Return the first 开多 TradeRecord of the 一买多头 sub-strategy."""
    buy1_pos = engine.strategy.positions[0]
    opens = [t for t in buy1_pos.trades if t.operate == Operate.LO]
    assert opens, "expected at least one 一买多头 open"
    return buy1_pos, opens[0]


# --------------------------------------------------------------- drain == run


def test_full_drain_matches_run_research(mini_backtest_bars):
    """Research mode: no yield points fire; drained report matches run()."""
    STRATEGY_CONFIG["sizing_model"] = "research"
    engine_run = _make_engine(mini_backtest_bars)
    report_run = engine_run.run(warmup_bars=5)

    engine_gen = _make_engine(mini_backtest_bars)
    gen = engine_gen.bar_generator(warmup_bars=5)
    assert not isinstance(gen, dict)
    yielded, report_gen = _drain(gen)

    assert yielded == []  # research mode has no equity/margin injection points
    assert "error" not in report_run
    assert report_gen == report_run
    assert engine_gen.equity_curve == engine_run.equity_curve


def test_full_drain_matches_run_risk(monkeypatch, mini_backtest_bars):
    """Risk mode: both yield kinds fire; drained output matches run() exactly."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    _patch_buy1_signals(monkeypatch)

    engine_run = _make_engine(mini_backtest_bars)
    report_run = engine_run.run(warmup_bars=5)

    engine_gen = _make_engine(mini_backtest_bars)
    gen = engine_gen.bar_generator(warmup_bars=5)
    assert not isinstance(gen, dict)
    yielded, report_gen = _drain(gen)

    # Exactly two yield kinds, strictly alternating pre_open -> post_bar.
    kinds = [item[0] for item in yielded]
    assert set(kinds) == {"pre_open", "post_bar"}
    assert kinds[0] == "pre_open"
    for idx in range(0, len(kinds), 2):
        assert kinds[idx] == "pre_open"
        assert kinds[idx + 1] == "post_bar"
    # Yield payload shape: (kind, dt, price, computed_equity, computed_margin).
    for item in yielded:
        assert len(item) == 5

    assert "error" not in report_run
    assert report_run["total_trades"] >= 1  # the injected 一买 signal traded
    assert report_gen == report_run
    assert engine_gen.equity_curve == engine_run.equity_curve
    assert engine_gen.equity_curve[0]["total_open_margin"] >= 0.0


# ------------------------------------------- override reaches position sizing


def test_pre_open_override_changes_position_sizing(monkeypatch, mini_backtest_bars):
    """An injected (equity, margin) override at pre_open changes lot sizing."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    _patch_buy1_signals(monkeypatch)

    # Baseline: plain run() records the default-sized open.
    engine_base = _make_engine(mini_backtest_bars)
    report_base = engine_base.run(warmup_bars=5)
    assert "error" not in report_base
    buy1_pos, open_trade = _first_long_open(engine_base)
    baseline_volume = open_trade.volume
    fill_dt = open_trade.dt
    fill_price = open_trade.price

    # Capture the computed (equity, margin) the engine itself produces at the
    # pre_open yield of the fill bar (send None everywhere).
    engine_probe = _make_engine(mini_backtest_bars)
    gen = engine_probe.bar_generator(warmup_bars=5)
    yielded, _ = _drain(gen)
    pre_open_at_fill = next(
        item for item in yielded if item[0] == "pre_open" and item[1] == fill_dt
    )
    _kind, _dt, yield_price, computed_equity, computed_margin = pre_open_at_fill
    assert yield_price == fill_price

    # Override run: inject 4x equity at exactly that pre_open yield.
    override_equity = computed_equity * 4
    engine_override = _make_engine(mini_backtest_bars)
    gen = engine_override.bar_generator(warmup_bars=5)
    _yielded, _report = _drain(gen, pre_open_overrides={fill_dt: (override_equity, 0.0)})
    _, override_trade = _first_long_open(engine_override)

    # Expected sizing straight from Position._size_open()'s formula.
    spec = _research_contract_spec("TEST")
    multiplier = int(spec.get("multiplier", 1))
    stop_distance = fill_price * buy1_pos.stop_loss / 10000
    risk_pct = STRATEGY_CONFIG["risk_per_trade_pct"]
    expected_base = int(floor(computed_equity * risk_pct / (stop_distance * multiplier)))
    expected_override = int(floor(override_equity * risk_pct / (stop_distance * multiplier)))

    assert baseline_volume == expected_base
    assert override_trade.dt == fill_dt
    assert override_trade.volume == expected_override
    assert override_trade.volume != baseline_volume
    # The probe engine (send None everywhere) matches the baseline exactly.
    assert engine_probe.equity_curve == engine_base.equity_curve


# ------------------------------------------------------------------ error path


def test_bar_generator_error_path_returns_dict(mini_backtest_bars):
    """Early setup failure returns the error dict, same as run()."""
    engine = _make_engine(mini_backtest_bars)
    engine.load_data = lambda: False
    gen = engine.bar_generator(warmup_bars=5)
    assert isinstance(gen, dict)
    assert gen["error"] == "数据加载失败"
    assert engine.run(warmup_bars=5) == gen


def test_short_data_error_matches_run(mini_backtest_bars):
    engine = _make_engine(mini_backtest_bars[:50])
    gen = engine.bar_generator(warmup_bars=5)
    assert isinstance(gen, dict)
    assert "error" in gen
    engine2 = _make_engine(mini_backtest_bars[:50])
    assert engine2.run(warmup_bars=5) == gen

"""A87 — Joint-clock portfolio replay + PortfolioLedger unit tests.

Validates the A87 joint/coordinated portfolio replay
(``sizing_model="risk" + portfolio_risk="on"``):

(a) ``PortfolioLedger`` aggregation (equity from PnL contributions without
    double-counting ``initial_capital``; margin totals / per-cluster sums,
    case-insensitive cluster membership; day-rollover bookkeeping;
    ``pre_open_injection_for`` reason priority and saturated-margin values);
(b) the live joint driver (real ``bar_generator()`` calls on synthetic bar
    fixtures): true shared numbers make ``max_margin_pct`` act as a
    total-portfolio cap; per-symbol / cluster caps and the daily loss limit
    block new opens via the saturated-margin mechanism; blocked symbols are
    portfolio-wide; the block clears at the next trading day; no position is
    ever force-closed; a symbol whose bar range ends stops contributing
    margin (A83 semantics) while its PnL contribution stays frozen;
(c) ``run()`` routing for every config combination, with the two pre-existing
    branches untouched.

Fixtures use >= 110 30-minute bars because ``_build_joint_report`` calls
``bar_generator()`` with its default ``warmup_bars=100`` (matching ``run()``).

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import chan_strategy.backtest_engine as be
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.portfolio_engine import PortfolioEngine
from chan_strategy.portfolio_ledger import PortfolioLedger
from chan_strategy.positions import Operate
from conftest import make_raw_bar

FREQ = "30分钟"
START = datetime(2024, 1, 2, 9, 0)
BARS_PER_DAY = 6          # 30-minute bars per synthetic day (09:00..11:30)
ONEM_PER_DAY = 180        # 1-minute bars per synthetic day
IC = 1_000_000.0

BUY1_SIGNALS = {
    f"{FREQ}_D1ZS_数据状态V260615": "充分_任意_任意_0",
    f"{FREQ}_D1ZS_结构状态V260615": "已确认_任意_任意_0",
    f"{FREQ}_D1BSP_一买V260615": "一买确认_任意_任意_0",
    f"{FREQ}_D1BI_方向V260615": "向上_任意_任意_0",
}

BUY2_SIGNALS = {
    f"{FREQ}_D1ZS_数据状态V260615": "充分_任意_任意_0",
    f"{FREQ}_D1ZS_结构状态V260615": "已确认_任意_任意_0",
    f"{FREQ}_D1ZS_位置V260615": "中枢上方_任意_任意_0",
    f"{FREQ}_D1BSP_二买V260615": "二买确认_任意_任意_0",
    f"{FREQ}_D1BI_方向V260615": "向上_任意_任意_0",
}


@pytest.fixture(autouse=True)
def restore_config():
    """Snapshot and restore the whole STRATEGY_CONFIG so tests never leak."""
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


# ------------------------------------------------------------------ fixtures

def _make_bars(closes: list[float], start: datetime = START) -> list:
    """Build 1-minute bars whose 30-minute resampled closes match ``closes``.

    Each 30-minute bar owns 30 1-minute bars stepping linearly from the
    previous 30-minute close to the target close, so the resampled 30-minute
    open equals the previous close and its close equals the target.
    """
    bars = []
    price = closes[0]
    prev_close = closes[0]
    i = 0
    for target in closes:
        delta = (target - prev_close) / 30
        for _ in range(30):
            day = start.date() + timedelta(days=(i // ONEM_PER_DAY))
            session_start = datetime.combine(day, start.time())
            dt = session_start + timedelta(minutes=i % ONEM_PER_DAY)
            open_ = price
            close = price + delta
            bars.append(make_raw_bar(i, dt, open_=open_, close=close))
            price = close
            i += 1
        prev_close = target
    return bars


def _flat_closes(n: int = 20 * BARS_PER_DAY, price: float = 100.0) -> list[float]:
    return [price] * n


def _patch_load_data(monkeypatch, bars_by_symbol: dict) -> None:
    """Route each engine's data load to the per-symbol fixture (None = load failure)."""
    def fake_load_data(self):
        bars = bars_by_symbol.get(self.symbol)
        if bars is None:
            return False
        self.bars = list(bars)
        return True

    monkeypatch.setattr(BacktestEngine, "load_data", fake_load_data)


def _patch_signals(monkeypatch, schedule: dict, per_symbol: dict | None = None) -> None:
    """Fire canned trade-freq signals per engine run.

    ``schedule`` maps a zero-based per-run call index (call k happens at loop
    bar ``warmup_bars + k``) to the signal dict returned for that call; every
    other call returns ``{}``.  Keyed on CZSC object identity so each engine
    run gets its own counter; strong references avoid id() reuse.

    When ``per_symbol`` is given it maps symbol -> schedule and overrides
    ``schedule``; CZSC objects register in the joint driver's deterministic
    first-tick processing order, which is ``sorted(per_symbol)``.
    """
    state: list = []  # list of [czsc_obj, next_call_index, schedule]
    ordered_symbols = sorted(per_symbol) if per_symbol else []

    def fake_get_all_signals(czsc_obj, freq, **kwargs):
        if freq != FREQ:
            return {}
        for entry in state:
            if entry[0] is czsc_obj:
                idx = entry[1]
                entry[1] = idx + 1
                return dict(entry[2].get(idx, {}))
        if per_symbol is not None:
            symbol = ordered_symbols[len(state)]
            entry_schedule = per_symbol.get(symbol, {})
        else:
            entry_schedule = schedule
        state.append([czsc_obj, 1, entry_schedule])
        return dict(entry_schedule.get(0, {}))

    monkeypatch.setattr(be, "get_all_signals", fake_get_all_signals)


def _capture_engines(monkeypatch) -> dict:
    """Spy on PortfolioEngine._make_symbol_engine to capture created engines."""
    created: dict = {}
    original = PortfolioEngine._make_symbol_engine

    def spy(self, symbol):
        engine = original(self, symbol)
        created[symbol] = engine
        return engine

    monkeypatch.setattr(PortfolioEngine, "_make_symbol_engine", spy)
    return created


def _position(engine: BacktestEngine, name: str):
    return next(p for p in engine.strategy.positions if p.name == name)


def _long_opens(engine: BacktestEngine, name: str = "一买多头") -> list:
    pos = _position(engine, name)
    return [t for t in pos.trades if t.operate == Operate.LO]


def _run_joint(symbols=("AAA", "BBB"), initial_capital: float = IC) -> dict:
    engine = PortfolioEngine(
        list(symbols), db_path="none", initial_capital=initial_capital
    )
    return engine.run()


def _risk_config(**overrides) -> None:
    """Base config for joint-replay driver tests (filter_freq disables the
    daily filter regardless of the 20 daily warmup bars)."""
    STRATEGY_CONFIG.update({
        "sizing_model": "risk",
        "portfolio_risk": "on",
        "filter_freq": "5分钟",
        "contract_specs": {
            "AAA": {"multiplier": 10, "tick": 1.0, "margin_rate": 0.05},
            "BBB": {"multiplier": 10, "tick": 1.0, "margin_rate": 0.05},
        },
    })
    STRATEGY_CONFIG.update(overrides)


# ------------------------------------------------------- PortfolioLedger unit

def _make_ledger(symbols=("AAA", "BBB"), clusters=None, cfg=None) -> PortfolioLedger:
    base = {
        "max_margin_pct": 0.5,
        "max_symbol_margin_pct": 1.0,
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 0.03,
        "daily_agg": "natural",
    }
    if cfg:
        base.update(cfg)
    return PortfolioLedger(list(symbols), IC, clusters or {}, config=base)


def test_ledger_equity_aggregation_no_double_count():
    """Shared equity = initial_capital + sum(contributions), capital counted once."""
    ledger = _make_ledger()
    assert ledger.equity == IC

    ledger.update_equity({"AAA": 1_500.0, "BBB": -500.0})
    assert ledger.equity == pytest.approx(IC + 1_000.0)

    # Recompute from the full dict each time (not incremental double counting).
    ledger.update_equity({"AAA": 2_000.0, "BBB": -500.0})
    assert ledger.equity == pytest.approx(IC + 1_500.0)


def test_ledger_margin_totals_and_case_insensitive_clusters():
    """margin_total / margin_by_cluster are currency sums; membership is case-insensitive."""
    ledger = _make_ledger(clusters={"grp": ["aaa"]})
    assert ledger.margin_total == 0.0
    assert ledger.margin_by_cluster == {"grp": 0.0}

    ledger.update_symbol_margin("AAA", 12_500.0)
    assert ledger.margin_total == pytest.approx(12_500.0)
    assert ledger.margin_by_cluster["grp"] == pytest.approx(12_500.0)

    ledger.update_symbol_margin("BBB", 8_000.0)
    assert ledger.margin_total == pytest.approx(20_500.0)
    assert ledger.margin_by_cluster["grp"] == pytest.approx(12_500.0)

    ledger.update_symbol_margin("AAA", 0.0)
    assert ledger.margin_total == pytest.approx(8_000.0)
    assert ledger.margin_by_cluster["grp"] == pytest.approx(0.0)


def test_ledger_trading_day_rollover_resets_limit():
    """A new trading day clears the limit and rebases day_start_equity."""
    ledger = _make_ledger(cfg={"daily_loss_limit_pct": 0.03})
    ledger.update_trading_day(datetime(2024, 1, 2, 9, 0))
    assert ledger.trading_day == datetime(2024, 1, 2).date()
    assert ledger.day_start_equity == IC

    ledger.update_equity({"AAA": -40_000.0})
    ledger.check_daily_loss_limit()
    assert ledger.daily_loss_limit_active is True
    assert len(ledger.loss_limit_triggers) == 1

    ledger.update_trading_day(datetime(2024, 1, 3, 9, 0))
    assert ledger.daily_loss_limit_active is False
    assert ledger.day_start_equity == pytest.approx(IC - 40_000.0)


def test_ledger_daily_loss_trigger_recorded_once():
    """The trigger fires once and records dt / trading_day / equity / day_pnl_pct."""
    ledger = _make_ledger(cfg={"daily_loss_limit_pct": 0.03})
    dt = datetime(2024, 1, 2, 14, 59)
    ledger.update_trading_day(dt)
    ledger.update_equity({"AAA": -31_000.0})
    ledger.check_daily_loss_limit()
    ledger.check_daily_loss_limit()  # already active: no duplicate record

    assert len(ledger.loss_limit_triggers) == 1
    trigger = ledger.loss_limit_triggers[0]
    assert trigger["dt"] == dt.isoformat(sep=" ")
    assert trigger["trading_day"] == "2024-01-02"
    assert trigger["equity"] == pytest.approx(IC - 31_000.0)
    assert trigger["day_pnl_pct"] == pytest.approx(-0.031)


def test_pre_open_injection_real_numbers_when_nothing_breached():
    """Unbreached state feeds the true shared equity / margin_total."""
    ledger = _make_ledger()
    ledger.update_symbol_margin("AAA", 12_500.0)
    equity, margin, reason = ledger.pre_open_injection_for("BBB")
    assert equity == pytest.approx(IC)
    assert margin == pytest.approx(12_500.0)
    assert reason is None


def test_pre_open_injection_saturates_and_prioritizes_reasons():
    """Blocked injections feed equity * max_margin_pct; daily-loss > symbol > cluster."""
    # Per-symbol cap breach.
    ledger = _make_ledger(cfg={"max_symbol_margin_pct": 0.01})
    ledger.update_symbol_margin("AAA", 12_500.0)  # > IC * 0.01 = 10_000
    equity, margin, reason = ledger.pre_open_injection_for("AAA")
    assert reason == "symbol_margin_cap"
    assert margin == pytest.approx(equity * ledger.max_margin_pct)
    # BBB (no own margin) is unaffected by AAA's per-symbol breach.
    _, margin_bbb, reason_bbb = ledger.pre_open_injection_for("BBB")
    assert reason_bbb is None
    assert margin_bbb == pytest.approx(12_500.0)

    # Cluster cap breach.
    ledger = _make_ledger(clusters={"grp": ["aaa", "BBB"]}, cfg={"cluster_gross_cap": 0.02})
    ledger.update_symbol_margin("AAA", 25_000.0)  # cluster 25_000 > IC * 0.02 = 20_000
    _, _, reason = ledger.pre_open_injection_for("BBB")
    assert reason == "cluster_gross_cap:grp"

    # Priority: daily loss beats per-symbol; per-symbol beats cluster.
    ledger = _make_ledger(
        clusters={"grp": ["aaa"]},
        cfg={"max_symbol_margin_pct": 0.01, "cluster_gross_cap": 0.001},
    )
    ledger.update_symbol_margin("AAA", 25_000.0)  # breaches both symbol and cluster caps
    assert ledger.pre_open_injection_for("AAA")[2] == "symbol_margin_cap"
    ledger.daily_loss_limit_active = True
    assert ledger.pre_open_injection_for("AAA")[2] == "daily_loss_limit"


# ------------------------------------------------------------ driver: basics

def test_joint_replay_no_trades_smoke(monkeypatch):
    """No signals: constant equity, zero margin, empty diagnostics, report shape."""
    _risk_config()
    bars = _make_bars(_flat_closes())
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": bars})
    _patch_signals(monkeypatch, {})

    report = _run_joint()

    assert report["portfolio_risk"] == "on"
    assert report["sizing_model"] == "risk"
    assert report["initial_capital"] == IC
    assert report["symbols"] == ["AAA", "BBB"]
    assert report["symbol_errors"] == {}
    assert report["blocked_opens"] == []
    assert report["loss_limit_triggers"] == []
    assert report["pairs"] == []
    assert report["flatten_on_breach"] == "not_implemented_see_A89"
    assert "flat_events" not in report
    assert len(report["equity_curve"]) == 20  # 120 trade bars, warmup 100
    for entry in report["equity_curve"]:
        assert entry["equity"] == pytest.approx(IC)
        assert entry["total_open_margin"] == pytest.approx(0.0)


def test_joint_equity_and_margin_aggregation(monkeypatch):
    """Ledger equity/margin equal the exact sum of per-symbol computed values."""
    _risk_config()
    closes = [100.0 + 0.05 * j for j in range(20 * BARS_PER_DAY)]
    bars = _make_bars(closes)
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": bars})
    _patch_signals(monkeypatch, {0: BUY1_SIGNALS})
    engines = _capture_engines(monkeypatch)

    report = _run_joint()

    final_close = closes[-1]
    expected_equity = IC
    expected_margin = 0.0
    for symbol in ("AAA", "BBB"):
        eq, margin = engines[symbol]._compute_equity_and_margin(final_close)
        expected_equity += eq - IC
        expected_margin += margin
    assert report["equity_curve"][-1]["equity"] == pytest.approx(expected_equity)
    assert report["equity_curve"][-1]["total_open_margin"] == pytest.approx(expected_margin)

    # Mid-curve consistency at an arbitrary tick after both symbols opened.
    buy1 = _position(engines["AAA"], "一买多头")
    assert buy1.pos != 0
    mid_idx = 110
    mid_dt = engines["AAA"].trade_bars[mid_idx].dt
    expected_mid = IC
    for symbol in ("AAA", "BBB"):
        pos = _position(engines[symbol], "一买多头")
        expected_mid += (closes[mid_idx] - pos.cost) * pos.volume * pos.contract_multiplier
    mid_entry = next(e for e in report["equity_curve"] if e["dt"] == mid_dt)
    assert mid_entry["equity"] == pytest.approx(expected_mid)

    # The last-processed symbol's own recorded curve carries the shared view.
    assert engines["BBB"].equity_curve[-1]["equity"] == pytest.approx(expected_equity)
    # The first-processed symbol's curve differs from its standalone view:
    # it already includes the other symbol's previous-tick contribution.
    standalone_aaa = IC + (final_close - buy1.cost) * buy1.volume * buy1.contract_multiplier
    assert engines["AAA"].equity_curve[-1]["equity"] != pytest.approx(standalone_aaa)


def test_data_error_symbol_is_excluded_and_recorded(monkeypatch):
    """A symbol whose bar_generator returns an error dict is excluded from the loop."""
    _risk_config()
    bars = _make_bars(_flat_closes())
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": None})
    _patch_signals(monkeypatch, {})

    report = _run_joint()

    assert report["symbol_errors"] == {"BBB": "数据加载失败"}
    assert report["symbols"] == ["AAA"]
    assert "error" in report["symbol_reports"]["BBB"]
    assert len(report["equity_curve"]) == 20
    assert report["equity_curve"][-1]["equity"] == pytest.approx(IC)


# ------------------------------------------------------------ driver: gating

def test_total_margin_cap_reduces_second_symbol_open(monkeypatch):
    """True shared numbers make max_margin_pct act as a total-portfolio cap.

    equity=1e6, max_margin_pct=0.02 -> cap 20_000.  AAA opens 250 lots
    (margin 12_500) first; at the same tick BBB's injected pre-open margin of
    12_500 lets the existing _size_open() formula fit only 150 lots — a real
    reduction by the unmodified positions.py formula, with no blocked_opens
    entries (nothing was saturated).
    """
    _risk_config(max_margin_pct=0.02)
    bars = _make_bars(_flat_closes())
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": bars})
    _patch_signals(monkeypatch, {0: BUY1_SIGNALS})
    engines = _capture_engines(monkeypatch)

    report = _run_joint()

    aaa_opens = _long_opens(engines["AAA"])
    bbb_opens = _long_opens(engines["BBB"])
    assert len(aaa_opens) == 1
    assert len(bbb_opens) == 1
    assert aaa_opens[0].volume == 250
    assert bbb_opens[0].volume == 150  # floor((20_000 - 12_500) / 50)
    assert aaa_opens[0].dt == bbb_opens[0].dt  # same joint tick
    assert _position(engines["BBB"], "一买多头").margin_cap_skip == 0
    assert report["blocked_opens"] == []


def test_per_symbol_cap_blocks_own_new_open_with_total_headroom(monkeypatch):
    """max_symbol_margin_pct blocks a symbol's own new opens once its own
    margin share exceeds the cap, even with total-portfolio headroom."""
    _risk_config(max_symbol_margin_pct=0.01)  # cap 10_000 per symbol
    bars = _make_bars(_flat_closes())
    _patch_load_data(monkeypatch, {"AAA": bars})
    _patch_signals(monkeypatch, {0: BUY1_SIGNALS, 3: BUY2_SIGNALS})
    engines = _capture_engines(monkeypatch)

    report = _run_joint(symbols=("AAA",))

    # 一买 opens (own margin share was 0 at its pre_open): 250 lots -> margin 12_500.
    aaa_buy1 = _position(engines["AAA"], "一买多头")
    assert len(_long_opens(engines["AAA"])) == 1
    assert _long_opens(engines["AAA"])[0].volume == 250
    # 二买 attempt at the next tick is blocked: 12_500 > 1e6 * 0.01.
    aaa_buy2 = _position(engines["AAA"], "二买多头")
    assert [t for t in aaa_buy2.trades if t.operate == Operate.LO] == []
    assert aaa_buy2.margin_cap_skip >= 1
    assert aaa_buy1.pos != 0  # the existing position is left alone

    blocked = [b for b in report["blocked_opens"] if b["reason"] == "symbol_margin_cap"]
    assert blocked, "expected symbol_margin_cap gating pressure to be recorded"
    assert all(b["symbol"] == "AAA" for b in blocked)
    expected_dt = engines["AAA"].trade_bars[104].dt  # attempt bar (signal at bar 103)
    assert expected_dt.isoformat(sep=" ") in {b["dt"] for b in blocked}
    # Total portfolio margin has headroom (12_500 << 1e6 * 0.5).
    assert report["equity_curve"][-1]["total_open_margin"] == pytest.approx(12_500.0)


def test_cluster_cap_blocks_cluster_mate_case_insensitive(monkeypatch):
    """cluster_gross_cap rejects a new open when the cluster's combined margin
    exceeds the cap; membership matching is case-insensitive."""
    _risk_config(
        corr_clusters={"grp": ["aaa", "BBB"]},  # mixed case on purpose
        cluster_gross_cap=0.001,                # cap 1_000
    )
    bars = _make_bars(_flat_closes())
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": bars})
    _patch_signals(monkeypatch, {0: BUY1_SIGNALS})
    engines = _capture_engines(monkeypatch)

    report = _run_joint()

    # AAA (sorted first) opens 250 lots -> cluster margin 12_500 > 1_000.
    assert _long_opens(engines["AAA"])[0].volume == 250
    # BBB's real open attempt at the same tick is rejected by the saturated feed.
    bbb_buy1 = _position(engines["BBB"], "一买多头")
    assert [t for t in bbb_buy1.trades if t.operate == Operate.LO] == []
    assert bbb_buy1.margin_cap_skip >= 1

    # The first blocked entry is BBB's real rejected attempt at the shared
    # tick; while the breach persists every later pre_open records
    # (speculative) gating pressure for both cluster members.
    blocked = report["blocked_opens"]
    assert blocked[0] == {
        "dt": engines["AAA"].trade_bars[101].dt.isoformat(sep=" "),
        "symbol": "BBB",
        "reason": "cluster_gross_cap:grp",
    }
    assert {b["reason"] for b in blocked} == {"cluster_gross_cap:grp"}
    assert {b["symbol"] for b in blocked} == {"AAA", "BBB"}


def test_daily_loss_limit_blocks_rest_of_day_then_clears(monkeypatch):
    """Once breached, new opens are blocked portfolio-wide for the rest of the
    trading day; the block clears at the next trading-day rollover."""
    _risk_config(
        stop_loss_1buy=1000,          # stop at -10% so positions go flat after the crash
        trailing_start_bp=100000,     # trailing stop never activates
        interval_1buy=0,              # allow same-day re-open attempts
        daily_loss_limit_pct=0.005,   # 0.5%
    )
    closes = _flat_closes()
    closes[103] = 95.5
    for j in range(104, len(closes)):
        closes[j] = 89.5
    bars = _make_bars(closes)
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": bars})
    # call 0 -> bar 100 signal (fill bar 101 @100); call 5 -> bar 105 signal
    # (attempt bar 106, blocked); call 12 -> bar 112 signal (fill bar 113, next day).
    _patch_signals(monkeypatch, {0: BUY1_SIGNALS, 5: BUY1_SIGNALS, 12: BUY1_SIGNALS})
    engines = _capture_engines(monkeypatch)

    report = _run_joint()

    # Triggered once, on the crash day, after the stop-outs.
    assert len(report["loss_limit_triggers"]) == 1
    trigger = report["loss_limit_triggers"][0]
    trade_bars = engines["AAA"].trade_bars
    assert trigger["dt"] == trade_bars[104].dt.isoformat(sep=" ")
    assert trigger["trading_day"] == str(trade_bars[104].dt.date())
    assert trigger["day_pnl_pct"] <= -0.005

    # Both symbols were blocked on the trigger day (portfolio-wide, not just
    # the triggerer); every blocked entry is on the trigger day.
    blocked = report["blocked_opens"]
    assert blocked, "expected daily_loss_limit gating pressure"
    assert {b["reason"] for b in blocked} == {"daily_loss_limit"}
    assert {b["symbol"] for b in blocked} == {"AAA", "BBB"}
    assert all(b["dt"].startswith(str(trade_bars[104].dt.date())) for b in blocked)
    attempt_dt = trade_bars[106].dt.isoformat(sep=" ")
    assert {(b["symbol"], b["dt"]) for b in blocked} >= {
        ("AAA", attempt_dt), ("BBB", attempt_dt)
    }

    for symbol in ("AAA", "BBB"):
        buy1 = _position(engines[symbol], "一买多头")
        opens = [t for t in buy1.trades if t.operate == Operate.LO]
        # Open #1 filled @100 on bar 101; the same-day attempt was rejected by
        # the saturated feed (margin_cap_skip); open #2 filled next day @89.5.
        assert len(opens) == 2
        assert opens[0].dt == trade_bars[101].dt
        assert opens[0].volume == 50
        assert opens[1].dt == trade_bars[113].dt
        assert opens[1].volume == 55
        assert buy1.margin_cap_skip >= 1
        # The only close is the strategy's own stop-loss, not a portfolio action.
        assert len(buy1.pairs) == 1
        assert "止损" in buy1.pairs[0]["reason"]


def test_daily_loss_limit_does_not_force_close_positions(monkeypatch):
    """A breach while positions are open leaves every position alone (A87 scope)."""
    _risk_config(
        stop_loss_1buy=1000,          # stop at 90; price only dips to 92 -> never fires
        trailing_start_bp=100000,
        daily_loss_limit_pct=0.005,
    )
    closes = _flat_closes()
    for j in range(103, len(closes)):
        closes[j] = 92.0
    bars = _make_bars(closes)
    _patch_load_data(monkeypatch, {"AAA": bars, "BBB": bars})
    _patch_signals(monkeypatch, {0: BUY1_SIGNALS})
    engines = _capture_engines(monkeypatch)

    report = _run_joint()

    assert len(report["loss_limit_triggers"]) == 1
    for symbol in ("AAA", "BBB"):
        buy1 = _position(engines[symbol], "一买多头")
        assert buy1.pos != 0, f"{symbol} position must still be open"
        assert buy1.pairs == [], f"{symbol} must have no closes at all"
        assert engines[symbol].strategy.get_combined_trades() == []
    assert report["pairs"] == []
    assert "flat_events" not in report
    assert report["flatten_on_breach"] == "not_implemented_see_A89"
    # Final shared equity = 1e6 + 2 * (92 - 100) * 50 * 10 (no costs: no closes).
    assert report["equity_curve"][-1]["equity"] == pytest.approx(992_000.0)


def test_symbol_margin_not_carried_past_symbol_end(monkeypatch):
    """A symbol with fewer bars stops contributing margin after its final bar
    (A83 semantics, live driver); its PnL contribution stays frozen."""
    _risk_config(stop_loss_1buy=1000, trailing_start_bp=100000)
    aaa_bars = _make_bars(_flat_closes(20 * BARS_PER_DAY))
    bbb_bars = _make_bars(_flat_closes(19 * BARS_PER_DAY))
    _patch_load_data(monkeypatch, {"AAA": aaa_bars, "BBB": bbb_bars})
    # Only BBB opens; AAA never trades and contributes zero margin throughout.
    _patch_signals(monkeypatch, {}, per_symbol={"AAA": {}, "BBB": {0: BUY1_SIGNALS}})
    engines = _capture_engines(monkeypatch)

    report = _run_joint()

    trade_bars = engines["AAA"].trade_bars
    margin_by_dt = {e["dt"]: e["total_open_margin"] for e in report["equity_curve"]}
    # 20 unique ticks (AAA's full traded range); BBB ended after bar 113.
    assert len(report["equity_curve"]) == 20
    assert margin_by_dt[trade_bars[100].dt] == pytest.approx(0.0)      # before the fill
    assert margin_by_dt[trade_bars[113].dt] == pytest.approx(2_500.0)  # BBB's last bar
    assert margin_by_dt[trade_bars[114].dt] == pytest.approx(0.0)      # not carried forward
    assert margin_by_dt[trade_bars[119].dt] == pytest.approx(0.0)
    # BBB's report was collected and its PnL contribution (0, flat prices) frozen.
    assert "error" not in report["symbol_reports"]["BBB"]
    assert report["equity_curve"][-1]["equity"] == pytest.approx(IC)
    # BBB's position is still open inside its own engine (nothing force-closed),
    # it simply no longer contributes outside its bar range.
    assert _position(engines["BBB"], "一买多头").pos != 0


# ------------------------------------------------------------------- routing

def test_run_routes_all_config_combinations(monkeypatch):
    """run() routes risk+on to the joint replay; the two pre-existing branches
    keep their original routing (only the new branch was added)."""
    calls: list[str] = []
    monkeypatch.setattr(
        PortfolioEngine, "_run_per_symbol",
        lambda self: calls.append("per_symbol") or {},
    )
    monkeypatch.setattr(
        PortfolioEngine, "_build_off_report",
        lambda self, results: calls.append("off") or {"route": "off"},
    )
    monkeypatch.setattr(
        PortfolioEngine, "_build_on_report",
        lambda self, results: calls.append("on") or {"route": "on"},
    )
    monkeypatch.setattr(
        PortfolioEngine, "_build_joint_report",
        lambda self: calls.append("joint") or {"route": "joint"},
    )

    engine = PortfolioEngine(["S1"], db_path="none")
    expectations = [
        ("research", "off", "off"),
        ("research", "on", "on"),
        ("risk", "off", "off"),
        ("risk", "on", "joint"),
    ]
    for sizing_model, portfolio_risk, expected in expectations:
        STRATEGY_CONFIG.update({
            "sizing_model": sizing_model,
            "portfolio_risk": portfolio_risk,
        })
        assert engine.run() == {"route": expected}, (sizing_model, portfolio_risk)

    # The joint branch never runs the per-symbol weight-based machinery.
    assert calls == ["per_symbol", "off", "per_symbol", "on", "per_symbol", "off", "joint"]

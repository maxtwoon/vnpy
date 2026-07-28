"""A48 P8b — Portfolio risk "off" full-engine equivalence regression.

Runs :class:`PortfolioEngine` end-to-end with ``portfolio_risk="off"`` on
deterministic synthetic data.  The stored snapshot represents the current
multi-symbol aggregate baseline; any future change that alters the default path
will produce a diff and fail.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from czsc import RawBar

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.portfolio_engine import PortfolioEngine


SNAPSHOT_PATH = Path(__file__).with_name("test_portfolio_risk_off_equivalence.snapshot.json")

DATASETS = [
    ("TEST_A", 15, 240, datetime(2024, 1, 2, 9, 0)),
    ("TEST_B", 20, 240, datetime(2024, 3, 4, 9, 0)),
]


def _make_mock_signals(open_at_call: int = 8, close_at_call: int = 10):
    """Return a deterministic get_all_signals replacement that forces one trade."""
    counters = {"trade": 0, "daily": 0}

    def _mock(czsc, freq, buy1_anchor=None, sell1_anchor=None):
        if freq == "日线":
            counters["daily"] += 1
            return {
                "日线_D1BI_方向V260615": "向上_任意_任意_50",
                "日线_D1ZS_位置V260615": "中枢内_任意_任意_50",
            }

        if freq != "30分钟":
            return {}

        counters["trade"] += 1
        call = counters["trade"]

        if call == open_at_call:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
            }

        if call == close_at_call:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_0",
            }

        return {
            "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
            "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
            "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
            "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
            "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
            "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
            "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
            "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
        }

    return _mock


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _fmt_dt(value):
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _serialize_report(report: dict) -> dict:
    return {
        "equity_curve": [
            {
                "dt": _fmt_dt(e.get("dt")),
                "equity": e.get("equity"),
            }
            for e in report["equity_curve"]
        ],
        "pairs": [
            {
                "symbol": p.get("symbol"),
                "strategy": p.get("strategy"),
                "open_dt": _fmt_dt(p.get("open_dt")),
                "close_dt": _fmt_dt(p.get("close_dt")),
                "open_price": p.get("open_price"),
                "close_price": p.get("close_price"),
                "pnl_pct": p.get("pnl_pct"),
                "volume": p.get("volume"),
                "contract_multiplier": p.get("contract_multiplier"),
                "bars_held": p.get("bars_held"),
                "reason": p.get("reason"),
                "reason_code": p.get("reason_code"),
            }
            for p in report["pairs"]
        ],
    }


def _with_symbol(bar: RawBar, symbol: str) -> RawBar:
    """Return a new RawBar identical to ``bar`` but with the given symbol.

    czsc 1.0.0rc8's RawBar is a Rust-backed immutable object, so we must create
    a new instance instead of mutating the attribute in place.
    """
    return RawBar(
        symbol=symbol,
        dt=bar.dt,
        freq=bar.freq,
        open=bar.open,
        close=bar.close,
        high=bar.high,
        low=bar.low,
        vol=bar.vol,
        amount=bar.amount,
        id=bar.id,
    )


def _make_bars_for_symbol(synthetic_1m_bars, symbol: str, days: int, per_day: int, start: datetime):
    bars = synthetic_1m_bars(days=days, per_day=per_day, start=start)
    return [_with_symbol(bar, symbol) for bar in bars]


def test_portfolio_risk_off_full_engine_equivalence(synthetic_1m_bars, monkeypatch):
    """``portfolio_risk='off'`` aggregate output must match the stored baseline."""
    STRATEGY_CONFIG["portfolio_risk"] = "off"
    def _fake_load_data(self):
        # Reset the deterministic signal mock for each symbol so every symbol
        # receives the same open/close signal timing independently.
        monkeypatch.setattr(backtest_module, "get_all_signals", _make_mock_signals(8, 10))
        symbol = self.symbol
        dataset = next(d for d in DATASETS if d[0] == symbol)
        _, days, per_day, start = dataset
        self.bars = _make_bars_for_symbol(synthetic_1m_bars, symbol, days, per_day, start)
        return True

    monkeypatch.setattr(BacktestEngine, "load_data", _fake_load_data)

    symbols = [d[0] for d in DATASETS]
    engine = PortfolioEngine(
        symbols=symbols,
        db_path="none",
    )
    report = engine.run()

    actual = _serialize_report(report)

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        pytest.skip(f"Baseline snapshot created at {SNAPSHOT_PATH}; re-run to compare.")

    baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert actual == baseline, "portfolio_risk='off' aggregate output differs from stored baseline."

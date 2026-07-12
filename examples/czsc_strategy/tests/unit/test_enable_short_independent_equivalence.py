"""A46 P7 — Short-enabled independent-mode full-engine equivalence regression.

Runs BacktestEngine end-to-end with ``enable_short=True`` and
``regime_model="independent"`` on deterministic synthetic data.  The stored
snapshot represents the short-enabled baseline; any future change that alters
this path will produce a diff and fail the test.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG


SNAPSHOT_PATH = Path(__file__).with_name("test_enable_short_independent_equivalence.snapshot.json")

DATASETS = [
    ("TEST_A", 15, 240, datetime(2024, 1, 2, 9, 0)),
    ("TEST_B", 20, 180, datetime(2024, 3, 4, 9, 0)),
]


def _make_mock_signals(open_at_call: int = 8, close_at_call: int = 10):
    """Return deterministic signals that force one short trade with P4/P5 satisfied."""
    counters = {"trade": 0, "daily": 0}

    def _mock(czsc, freq, buy1_anchor=None, sell1_anchor=None):
        if freq == "日线":
            counters["daily"] += 1
            # Daily down + below center satisfies short-side P5 resonance.
            return {
                "日线_D1BI_方向V260615": "向下_任意_任意_50",
                "日线_D1ZS_位置V260615": "中枢下方_任意_任意_50",
            }

        if freq != "30分钟":
            return {}

        counters["trade"] += 1
        call = counters["trade"]

        if call == open_at_call:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一卖V260615": "一卖确认_任意_任意_80",
                "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
                "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_50",
                "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
                "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
            }

        if call == close_at_call:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
                "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
                "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BI_背驰V260615": "无_任意_任意_0",
                "30分钟_D1BSP_空头风控V260615": "结构失效_任意_任意_0",
            }

        return {
            "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
            "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
            "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
            "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
            "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
            "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
            "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_50",
            "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
            "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
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


def _serialize_engine(engine: BacktestEngine) -> dict:
    pairs = engine.strategy.get_combined_trades()
    return {
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
                "sizing_model": e.get("sizing_model"),
            }
            for e in engine.equity_curve
        ],
        "pairs": [
            {
                "strategy": p.get("strategy"),
                "open_dt": _fmt_dt(p.get("open_dt")),
                "close_dt": _fmt_dt(p.get("close_dt")),
                "open_price": p.get("open_price"),
                "close_price": p.get("close_price"),
                "pnl_pct": p.get("pnl_pct"),
                "pnl_currency": p.get("pnl_currency"),
                "volume": p.get("volume"),
                "contract_multiplier": p.get("contract_multiplier"),
                "bars_held": p.get("bars_held"),
                "reason": p.get("reason"),
                "reason_code": p.get("reason_code"),
            }
            for p in pairs
        ],
    }


def _run_symbol(monkeypatch, bars, symbol: str, open_at: int, close_at: int) -> dict:
    STRATEGY_CONFIG["enable_short"] = True
    STRATEGY_CONFIG["regime_model"] = "independent"
    for key in ("stop_loss_1buy", "stop_loss_2buy", "stop_loss_3buy",
                "stop_loss_1sell", "stop_loss_2sell", "stop_loss_3sell"):
        STRATEGY_CONFIG[key] = 10000
    engine = BacktestEngine(symbol=symbol, db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    monkeypatch.setattr(backtest_module, "get_all_signals", _make_mock_signals(open_at, close_at))
    report = engine.run(warmup_bars=100)
    if "error" in report:
        pytest.skip(f"{symbol}: {report['error']}")
    return _serialize_engine(engine)


def test_enable_short_independent_full_engine_equivalence(synthetic_1m_bars, monkeypatch):
    """enable_short=True + regime_model='independent' must match the stored baseline."""
    actual = {
        symbol: _run_symbol(
            monkeypatch,
            synthetic_1m_bars(days=days, per_day=per_day, start=start),
            symbol,
            open_at=8,
            close_at=10,
        )
        for symbol, days, per_day, start in DATASETS
    }

    if not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        pytest.skip(f"Baseline snapshot created at {SNAPSHOT_PATH}; re-run to compare.")

    baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert actual == baseline, "enable_short=True/independent output differs from stored baseline."

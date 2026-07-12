"""Unit tests for the A37 Phase 1 dead-factor equivalence checker."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import diagnostics.phase1_dead_factor_equivalence as p1
from diagnostics.phase1_dead_factor_equivalence import (
    DEFAULT_ENABLE_SHORT_SYMBOLS,
    DEFAULT_SYMBOLS,
    DISCLAIMER,
    _baseline_factories,
    _diff_trades,
    _run_leg,
    main,
)


def _sample_trade(**overrides: Any) -> dict[str, Any]:
    defaults = {
        "strategy": "二买多头",
        "open_dt": datetime(2024, 6, 1, 9, 0),
        "open_price": 100.0,
        "close_dt": datetime(2024, 6, 10, 15, 0),
        "close_price": 101.0,
        "pnl_pct": 0.01,
        "reason_code": "trailing_stop",
        "bars_held": 100,
    }
    defaults.update(overrides)
    return defaults


def test_diff_trades_identical_pairs_are_unchanged() -> None:
    trades = [_sample_trade()]
    diff = _diff_trades(trades, trades)
    assert diff["summary"]["unchanged_count"] == 1
    assert diff["summary"]["removed_count"] == 0
    assert diff["summary"]["added_count"] == 0
    assert diff["summary"]["changed_count"] == 0


def test_diff_trades_detects_removed_added_and_changed() -> None:
    base = [
        _sample_trade(strategy="二买多头", open_dt=datetime(2024, 1, 1)),
        _sample_trade(strategy="三买多头", open_dt=datetime(2024, 2, 1)),
    ]
    current = [
        _sample_trade(strategy="二买多头", open_dt=datetime(2024, 1, 1)),
        _sample_trade(strategy="一买多头", open_dt=datetime(2024, 3, 1)),
    ]
    diff = _diff_trades(base, current)
    assert diff["summary"]["removed_count"] == 1
    assert diff["summary"]["added_count"] == 1
    assert diff["summary"]["changed_count"] == 0


def test_diff_trades_detects_reason_change() -> None:
    base = [_sample_trade(reason_code="stop_loss")]
    current = [_sample_trade(reason_code="signal_exit")]
    diff = _diff_trades(base, current)
    assert diff["summary"]["changed_count"] == 1
    assert diff["summary"]["unchanged_count"] == 0


def test_diff_trades_detects_close_dt_change() -> None:
    base = [_sample_trade(close_dt=datetime(2024, 6, 9, 15, 0))]
    current = [_sample_trade(close_dt=datetime(2024, 6, 10, 15, 0))]
    diff = _diff_trades(base, current)
    assert diff["summary"]["changed_count"] == 1


def test_diff_trades_treats_tiny_pnl_differences_as_unchanged() -> None:
    base = [_sample_trade(pnl_pct=0.01)]
    current = [_sample_trade(pnl_pct=0.010000000000000001)]
    diff = _diff_trades(base, current)
    assert diff["summary"]["unchanged_count"] == 1


class _FakeStrategy:
    def __init__(self, trades: list[dict[str, Any]]) -> None:
        self._trades = trades

    def get_combined_trades(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self._trades]


class _FakeEngineIdentical:
    """Always returns the same trade pair so baseline == current."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    def run(self) -> dict[str, Any]:
        self.strategy = _FakeStrategy([_sample_trade()])
        return {}


class _FakeEngineDifferent:
    """Returns different trades on the first (baseline) and second (current) call."""

    _call_count = 0

    def __init__(self, **kwargs: Any) -> None:
        pass

    def run(self) -> dict[str, Any]:
        _FakeEngineDifferent._call_count += 1
        if _FakeEngineDifferent._call_count % 2 == 1:
            self.strategy = _FakeStrategy([_sample_trade(open_dt=datetime(2024, 1, 1))])
        else:
            self.strategy = _FakeStrategy([_sample_trade(open_dt=datetime(2024, 2, 1))])
        return {}


def test_run_leg_equivalent_when_baseline_and_current_match(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(p1, "BacktestEngine", _FakeEngineIdentical)
    monkeypatch.setattr(p1, "_dominant_symbol", lambda db_path, table_name, start, end: "TEST")

    leg = _run_leg(tmp_path / "fake.db", ["TEST"], "2024-01-01", "2024-12-31", enable_short=False)
    assert leg["equivalent"] is True
    assert leg["per_symbol"]["TEST"]["diff"]["summary"]["unchanged_count"] == 1


def test_run_leg_not_equivalent_when_trades_differ(
    monkeypatch, tmp_path: Path
) -> None:
    _FakeEngineDifferent._call_count = 0
    monkeypatch.setattr(p1, "BacktestEngine", _FakeEngineDifferent)
    monkeypatch.setattr(p1, "_dominant_symbol", lambda db_path, table_name, start, end: "TEST")

    leg = _run_leg(tmp_path / "fake.db", ["TEST"], "2024-01-01", "2024-12-31", enable_short=False)
    assert leg["equivalent"] is False
    diff = leg["per_symbol"]["TEST"]["diff"]
    assert diff["summary"]["removed_count"] == 1
    assert diff["summary"]["added_count"] == 1


def test_baseline_factories_add_dead_factor_to_exits() -> None:
    from chan_strategy import positions as pos_mod

    current_buy = pos_mod.create_second_buy_position
    current_sell = pos_mod.create_second_sell_position

    with _baseline_factories():
        # Access the factories through the module so the monkeypatch is visible.
        buy_pos = pos_mod.create_second_buy_position("TEST", enable_daily_filter=False)
        sell_pos = pos_mod.create_second_sell_position("TEST", enable_daily_filter=False)
        # The A37 baseline dead factor is still injected; the 背驰=失效 value it
        # referenced was removed in A43, so we only check the factor name remains.
        assert any("方向反转且在中枢内" == f.name for f in buy_pos.exits[0].factors)
        assert any("方向反转且在中枢内" == f.name for f in sell_pos.exits[0].factors)

    # Factories are restored after the context manager exits.
    assert pos_mod.create_second_buy_position is current_buy
    assert pos_mod.create_second_sell_position is current_sell


def test_cli_missing_db_writes_report_and_exits_one(tmp_path: Path) -> None:
    out_json = tmp_path / "phase1_report.json"
    argv = [
        "--db-path",
        str(tmp_path / "missing.db"),
        "--out-json",
        str(out_json),
        "--symbols",
        "TEST1",
        "TEST2",
        "--enable-short-symbols",
        "TEST3",
    ]
    assert main(argv) == 1

    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["disclaimer"] == DISCLAIMER
    assert "long_leg" in report
    assert "short_leg" in report
    assert report["equivalent"] is False
    assert report["long_leg"]["per_symbol"]["TEST1"]["status"] == "unavailable"
    assert "GOAL PASSED" not in json.dumps(report)


def test_source_contains_no_trading_interface_tokens() -> None:
    root = Path(__file__).resolve().parents[2]
    source_path = root / "diagnostics" / "phase1_dead_factor_equivalence.py"
    source = source_path.read_text(encoding="utf-8")
    forbidden = ["send_order", "cancel_order", "buy(", "sell(", "short(", "cover("]
    for token in forbidden:
        assert token not in source, f"Forbidden trading-interface token: {token}"


def test_default_symbol_lists_cover_required_scope() -> None:
    assert len(DEFAULT_SYMBOLS) >= 2
    assert len(DEFAULT_ENABLE_SHORT_SYMBOLS) >= 1

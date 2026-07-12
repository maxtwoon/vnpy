"""Unit tests for the A40 unified position sizing report.

RESEARCH-ONLY, not a trading recommendation.
"""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from diagnostics.run_position_sizing_report import (
    _classify_exit,
    _contract_spec_crosscheck,
    _simnow_risk_caliber,
    _stop_trigger_price,
    main,
)


@pytest.fixture(autouse=True)
def restore_config():
    saved = {
        "sizing_model": STRATEGY_CONFIG.get("sizing_model", "research"),
        "stop_execution_model": STRATEGY_CONFIG.get("stop_execution_model", "close"),
    }
    yield
    STRATEGY_CONFIG.update(saved)


def test_stop_trigger_price_long_and_short():
    assert _stop_trigger_price(100.0, 200, "long") == pytest.approx(98.0)
    assert _stop_trigger_price(100.0, 200, "short") == pytest.approx(102.0)


def test_classify_exit_close_model_is_close_based():
    pair = {
        "strategy": "一买多头",
        "open_price": 100.0,
        "close_price": 96.0,
        "reason_code": "stop_loss",
    }
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    info = _classify_exit(pair, "close")
    assert info["is_stop_exit"] is True
    assert info["exit_type"] == "close_based"
    assert info["stop_distance_price"] == pytest.approx(2.0)


def test_classify_exit_intrabar_touch_based():
    pair = {
        "strategy": "一买多头",
        "open_price": 100.0,
        "close_price": 98.0,
        "reason_code": "stop_loss",
    }
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    info = _classify_exit(pair, "intrabar")
    assert info["exit_type"] == "touch_based"


def test_classify_exit_intrabar_gap_fill():
    pair = {
        "strategy": "一买多头",
        "open_price": 100.0,
        "close_price": 95.0,
        "reason_code": "stop_loss",
    }
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    info = _classify_exit(pair, "intrabar")
    assert info["exit_type"] == "gap_fill"


def test_simnow_risk_caliber_is_pending_placeholder():
    caliber = _simnow_risk_caliber()
    assert caliber["status"] == "not_available_pending_A41"
    assert "not fabricated" in caliber["note"]


def test_contract_spec_crosscheck_passes_for_all_specs():
    result = _contract_spec_crosscheck()
    for symbol, data in result.items():
        assert data["crosscheck_pass"] is True
        assert data["stop_distance_price_at_100"] == pytest.approx(
            100.0 - data["long_trigger_at_100"]
        )
        assert data["stop_distance_price_at_100"] == pytest.approx(
            data["short_trigger_at_100"] - 100.0
        )


def _make_fake_engine_and_report(sizing_model: str):
    fake_pair = {
        "open_dt": datetime(2024, 1, 1, 10, 0),
        "close_dt": datetime(2024, 1, 2, 10, 0),
        "open_price": 100.0,
        "close_price": 96.0,
        "pnl_pct": -0.04,
        "pnl_currency": -4.0,
        "volume": 1,
        "contract_multiplier": 1,
        "bars_held": 10,
        "reason": "止损",
        "reason_code": "stop_loss",
        "strategy": "一买多头",
    }

    mock_engine = MagicMock()
    mock_engine.symbol = "TEST"
    mock_engine.equity_curve = [
        {
            "dt": datetime(2024, 1, 2, 10, 0),
            "price": 96.0,
            "equity": 996000.0,
            "positions": 0,
            "long_exposure": 0.0,
            "short_exposure": 0.0,
            "net_exposure": 0.0,
            "gross_exposure": 0.0,
            "both_long_short": False,
            "sizing_model": sizing_model,
            "total_open_margin": 0.0,
            "margin_utilization_pct": 0.0,
        }
    ]
    mock_engine.strategy.get_combined_trades.return_value = [fake_pair]

    if sizing_model == "research":
        sizing_caveat = (
            "当前为信号研究模式（方向型仓位+事后加权），"
            "未建模合约乘数/资金上限/复利，仅评估信号有效性。"
        )
    else:
        sizing_caveat = None

    fake_report = {
        "symbol": "TEST",
        "sizing_model": sizing_model,
        "sizing_caveat": sizing_caveat,
        "stop_execution_model": "close",
        "total_trades": 1,
        "win_rate": 0.0,
        "total_return_pct": -0.4,
        "max_drawdown_pct": 0.4,
        "sharpe_ratio": 0.0,
        "final_equity": 996000.0,
        "max_total_open_margin": 0.0,
        "max_margin_utilization_pct": 0.0,
        "final_total_open_margin": 0.0,
    }
    return mock_engine, fake_report


def test_main_runs_without_db_via_monkeypatch(tmp_path):
    """Smoke-test the report wiring with a mocked BacktestEngine."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["stop_execution_model"] = "close"

    mock_engine, fake_report = _make_fake_engine_and_report("risk")

    with patch("diagnostics.run_position_sizing_report.BacktestEngine") as mock_be:
        mock_be.return_value = mock_engine
        mock_engine.run.return_value = fake_report
        out_json = tmp_path / "report.json"
        with patch("sys.argv", [
            "run_position_sizing_report.py",
            "--symbols", "TEST",
            "--sizing-model", "risk",
            "--start-date", "2024-01-01",
            "--end-date", "2024-01-02",
            "--out-json", str(out_json),
        ]):
            result = main()

    assert result["sizing_model"] == "risk"
    assert result["stop_execution_model"] == "close"
    assert result["summary"]["total_trades"] == 1
    assert result["summary"]["close_based_stop_exits"] == 1
    assert result["simnow_risk_caliber"]["status"] == "not_available_pending_A41"
    assert result["disclaimer"] == "Diagnostic only, not a trading recommendation."
    assert "exchange-minimum margin rates" in result["scope"]
    assert result.get("sizing_caveat") is None

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["trades"][0]["pnl_currency"] == -4.0
    assert payload.get("sizing_caveat") is None


def test_main_surfaces_sizing_caveat_in_research_mode(tmp_path):
    """When the underlying backtest uses sizing_model='research', the JSON report
    must carry the sizing_caveat in its body, not just on the console."""
    STRATEGY_CONFIG["sizing_model"] = "research"
    STRATEGY_CONFIG["stop_execution_model"] = "close"

    mock_engine, fake_report = _make_fake_engine_and_report("research")

    with patch("diagnostics.run_position_sizing_report.BacktestEngine") as mock_be:
        mock_be.return_value = mock_engine
        mock_engine.run.return_value = fake_report
        out_json = tmp_path / "report.json"
        with patch("sys.argv", [
            "run_position_sizing_report.py",
            "--symbols", "TEST",
            "--sizing-model", "research",
            "--start-date", "2024-01-01",
            "--end-date", "2024-01-02",
            "--out-json", str(out_json),
        ]):
            result = main()

    assert result["sizing_model"] == "research"
    assert result["sizing_caveat"] == (
        "当前为信号研究模式（方向型仓位+事后加权），"
        "未建模合约乘数/资金上限/复利，仅评估信号有效性。"
    )

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["sizing_caveat"] == result["sizing_caveat"]

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

import export_simnow_replay_snapshot as snapshot_mod  # noqa: E402
from export_simnow_replay_snapshot import (
    _filter_trades_for_concentration,  # noqa: E402
    _consecutive_loss_breakdown,
    _resolve_risk_start,
    _risk_for_day,
    build_snapshot,
)


def test_consecutive_loss_breakdown_includes_streak_rows():
    daily = pd.DataFrame(
        {
            "equity": [1.0, 0.999, 0.998, 0.9995, 0.999, 0.9987, 0.9982],
            "daily_return": [0.0, -0.001, -0.001001, 0.001503, -0.0005, -0.0003003, -0.0005007],
        },
        index=pd.to_datetime(
            [
                "2026-07-18",
                "2026-07-19",
                "2026-07-20",
                "2026-07-21",
                "2026-07-22",
                "2026-07-23",
                "2026-07-24",
            ]
        ).date,
    )

    result = _consecutive_loss_breakdown(daily)

    assert result["days"] == 3
    assert result["start_date"] == "2026-07-22"
    assert result["end_date"] == "2026-07-24"
    assert result["cumulative_return_pct"] == pytest.approx(-0.1301)
    assert result["rows"] == [
        {"date": "2026-07-22", "daily_return_pct": pytest.approx(-0.05), "equity": 0.999},
        {"date": "2026-07-23", "daily_return_pct": pytest.approx(-0.03003), "equity": 0.9987},
        {"date": "2026-07-24", "daily_return_pct": pytest.approx(-0.05007), "equity": 0.9982},
    ]


def test_consecutive_loss_breakdown_is_empty_without_losses():
    daily = pd.DataFrame(
        {
            "equity": [1.0, 1.001],
            "daily_return": [0.0, 0.001],
        },
        index=pd.to_datetime(["2026-07-23", "2026-07-24"]).date,
    )

    result = _consecutive_loss_breakdown(daily)

    assert result["days"] == 0
    assert result["start_date"] is None
    assert result["rows"] == []


def _stale_segment_daily() -> pd.DataFrame:
    """Daily portfolio frame with a fixed historical losing segment.

    Mirrors the 2023-06-19~2023-06-28 stale segment seen on 2026-07-24/27:
    a 6-day losing streak deep in the replay history, followed by recovery,
    one mild up-day and one mild down-day at the observation date.
    """
    dates = pd.to_datetime(
        [
            "2023-06-19",
            "2023-06-20",
            "2023-06-21",
            "2023-06-22",
            "2023-06-23",
            "2023-06-24",
            "2023-06-25",
            "2026-07-27",
            "2026-07-28",
        ]
    ).date
    daily_return = [-0.001] * 6 + [0.01, 0.001, -0.0005]
    equity = [1.0]
    for ret in daily_return[1:]:
        equity.append(equity[-1] * (1 + ret))
    return pd.DataFrame(
        {
            "equity": equity,
            "daily_return": daily_return,
            "gross_exposure": [0.1] * 9,
            "net_exposure": [0.1] * 9,
            "long_exposure": [0.1] * 9,
            "short_exposure": [0.0] * 9,
            "both_long_short_symbols": [0] * 9,
        },
        index=dates,
    )


def test_risk_for_day_full_history_keeps_stale_segment_without_window():
    daily = _stale_segment_daily()

    risk = _risk_for_day(daily, [], date(2026, 7, 28))

    assert risk["consecutive_loss"]["days"] == 6
    assert risk["consecutive_loss"]["start_date"] == "2023-06-19"
    # Peak is the first equity (1.0); trough after five further -0.1% days.
    expected_dd = (daily["equity"].iloc[5] / 1.0 - 1) * 100
    assert risk["drawdown_pct"] == pytest.approx(expected_dd, abs=1e-9)
    assert risk["drawdown_pct"] < -0.4


def test_risk_for_day_windows_metrics_to_risk_start():
    daily = _stale_segment_daily()

    risk = _risk_for_day(daily, [], date(2026, 7, 28), risk_start=date(2026, 7, 27))

    # Inside the window only the single 2026-07-28 down-day counts.
    assert risk["consecutive_loss"]["days"] == 1
    assert risk["consecutive_loss"]["start_date"] == "2026-07-28"
    # cummax is chronological: 07-27 sets the peak, 07-28 dips -0.05% below it.
    assert risk["drawdown_pct"] == pytest.approx(-0.05, abs=1e-9)


def test_risk_for_day_risk_start_after_day_falls_back_to_day_row():
    daily = _stale_segment_daily()

    risk = _risk_for_day(daily, [], date(2026, 7, 28), risk_start=date(2026, 8, 1))

    assert risk["drawdown_pct"] == 0.0
    assert risk["consecutive_loss"]["days"] == 1
    assert risk["daily_return_pct"] == pytest.approx(-0.05, abs=1e-9)


def test_resolve_risk_start_prefers_explicit_argument():
    resolved, source = _resolve_risk_start("2026-07-20", False, loader=lambda: "2026-07-27")

    assert resolved == date(2026, 7, 20)
    assert source == "argument"


def test_resolve_risk_start_falls_back_to_observation_window_config():
    resolved, source = _resolve_risk_start("", False, loader=lambda: "2026-07-27")

    assert resolved == date(2026, 7, 27)
    assert source == "observation_window_config"


def test_resolve_risk_start_full_history_flag_disables_config():
    resolved, source = _resolve_risk_start("", True, loader=lambda: "2026-07-27")

    assert resolved is None
    assert source == "full_history"


def test_resolve_risk_start_without_config_keeps_full_history():
    resolved, source = _resolve_risk_start("", False, loader=lambda: "")

    assert resolved is None
    assert source == "full_history"


class _FakeStrategy:
    def get_combined_trades(self):
        return []


class _FakeEngine:
    def __init__(self):
        self.signal_history = []
        self.strategy = _FakeStrategy()
        self.equity_curve = [
            {
                "dt": datetime(2023, 6, 19, 14, 59),
                "equity": 1.0,
                "long_exposure": 0.1,
                "short_exposure": 0.0,
                "net_exposure": 0.1,
                "gross_exposure": 0.1,
                "both_long_short": False,
            },
            {
                "dt": datetime(2023, 6, 20, 14, 59),
                "equity": 0.99,
                "long_exposure": 0.1,
                "short_exposure": 0.0,
                "net_exposure": 0.1,
                "gross_exposure": 0.1,
                "both_long_short": False,
            },
            {
                "dt": datetime(2026, 7, 27, 14, 59),
                "equity": 1.0,
                "long_exposure": 0.1,
                "short_exposure": 0.0,
                "net_exposure": 0.1,
                "gross_exposure": 0.1,
                "both_long_short": False,
            },
            {
                "dt": datetime(2026, 7, 28, 14, 59),
                "equity": 1.001,
                "long_exposure": 0.1,
                "short_exposure": 0.0,
                "net_exposure": 0.1,
                "gross_exposure": 0.1,
                "both_long_short": False,
            },
        ]


def _patch_snapshot_db(monkeypatch):
    monkeypatch.setattr(snapshot_mod, "_db_table_ranges", lambda db_path, symbols: {})
    monkeypatch.setattr(snapshot_mod, "_latest_db_date", lambda ranges: "")
    monkeypatch.setattr(
        snapshot_mod,
        "_run_symbol",
        lambda db_path, symbol, start, end, cost_factor: {
            "symbol": symbol,
            "data_symbol": symbol,
            "engine": _FakeEngine(),
        },
    )


def test_build_snapshot_records_risk_window_in_meta(monkeypatch):
    _patch_snapshot_db(monkeypatch)

    payload = build_snapshot(
        Path("dummy.db"), "2022-01-01", "2026-07-28", "2026-07-28", 1.0, risk_start="2026-07-27"
    )

    assert payload["meta"]["risk_window_start"] == "2026-07-27"
    assert payload["meta"]["risk_window_source"] == "argument"
    # The 2023 losing day is outside the window: drawdown must not include it.
    assert payload["risk"]["drawdown_pct"] > -0.2


def test_build_snapshot_defaults_to_observation_window_config(monkeypatch):
    _patch_snapshot_db(monkeypatch)
    monkeypatch.setattr(snapshot_mod, "load_observation_start_date", lambda: "2026-07-27")

    payload = build_snapshot(Path("dummy.db"), "2022-01-01", "2026-07-28", "2026-07-28", 1.0)

    assert payload["meta"]["risk_window_start"] == "2026-07-27"
    assert payload["meta"]["risk_window_source"] == "observation_window_config"


def test_build_snapshot_full_history_flag_ignores_config(monkeypatch):
    _patch_snapshot_db(monkeypatch)
    monkeypatch.setattr(snapshot_mod, "load_observation_start_date", lambda: "2026-07-27")

    payload = build_snapshot(
        Path("dummy.db"), "2022-01-01", "2026-07-28", "2026-07-28", 1.0, full_history_risk=True
    )

    assert payload["meta"]["risk_window_start"] == ""
    assert payload["meta"]["risk_window_source"] == "full_history"
    assert payload["risk"]["drawdown_pct"] < -0.5


def _trade(symbol, strategy, close_dt, pnl=0.01):
    return {
        "symbol": symbol,
        "strategy": strategy,
        "close_dt": close_dt,
        "weighted_pnl_pct": pnl * 100 / 5,
    }


def test_filter_trades_for_concentration_respects_rolling_window():
    day = date(2026, 7, 28)
    trades = [
        _trade("A888", "二买多头", datetime(2026, 7, 28, 15, 0)),     # day itself: in
        _trade("A888", "二买多头", datetime(2026, 5, 30, 15, 0)),     # exactly 60 days back: in
        _trade("RB888", "三买多头", datetime(2026, 5, 29, 15, 0)),    # 61 days back: out
        _trade("RB888", "三买多头", None),                            # no close_dt: out
        _trade("SC888", "一买多头", datetime(2026, 7, 29, 9, 0)),     # after day: out
    ]

    kept = _filter_trades_for_concentration(trades, day, 60)

    assert [t["symbol"] for t in kept] == ["A888", "A888"]


def test_risk_for_day_concentration_uses_rolling_window_and_marks_sample():
    daily = _stale_segment_daily()
    day = date(2026, 7, 28)
    trades = [
        _trade("A888", "二买多头", datetime(2026, 7, 20, 15, 0), pnl=0.03),
        _trade("RB888", "三买多头", datetime(2026, 7, 21, 15, 0), pnl=-0.01),
        _trade("SC888", "一买多头", datetime(2023, 6, 20, 15, 0), pnl=0.5),  # outside window
    ]

    risk = _risk_for_day(
        daily, trades, day,
        risk_start=date(2026, 7, 27),
        concentration_window_days=60,
        concentration_min_trades=5,
    )

    # Only the two in-window trades participate; the 2023 whale is excluded.
    assert risk["symbol_concentration"]["top1_abs_share"] == pytest.approx(0.75, abs=1e-9)
    assert {row["name"] for row in risk["strategy_concentration"]["rows"]} == {"二买多头", "三买多头"}
    sample = risk["concentration_sample"]
    assert sample["window_days"] == 60
    assert sample["min_trades"] == 5
    assert sample["trade_count"] == 2
    assert sample["insufficient_sample"] is True


def test_risk_for_day_concentration_sufficient_sample_flag():
    daily = _stale_segment_daily()
    day = date(2026, 7, 28)
    trades = [
        _trade("A888", "二买多头", datetime(2026, 7, 20, 15, 0)),
        _trade("A888", "二买多头", datetime(2026, 7, 21, 15, 0)),
        _trade("RB888", "三买多头", datetime(2026, 7, 22, 15, 0)),
        _trade("SC888", "一买多头", datetime(2026, 7, 23, 15, 0)),
        _trade("ZN888", "二买多头", datetime(2026, 7, 24, 15, 0)),
    ]

    risk = _risk_for_day(daily, trades, day, concentration_window_days=60, concentration_min_trades=5)

    assert risk["concentration_sample"]["trade_count"] == 5
    assert risk["concentration_sample"]["insufficient_sample"] is False

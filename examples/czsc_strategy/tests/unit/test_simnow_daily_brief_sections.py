import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_brief_sections import (  # noqa: E402
    build_delayed_replay_section_lines,
    build_environment_capture_section_lines,
    build_risk_source_breakdown_section_lines,
    build_threshold_diagnostics_section_lines,
)


def test_environment_capture_section_lines_match_daily_brief_contract():
    summary = {
        "environment_capture": {
            "ticks": 4,
            "contracts_count": 18023,
            "accounts": 1,
            "subscribed_count": 5,
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "tick_counts_by_symbol": {"AP888": 2, "RB888": 2},
            "zero_tick_subscribed_symbols": ["ZN888"],
        }
    }

    assert build_environment_capture_section_lines(summary) == [
        "## SimNow 环境采集",
        "",
        "- ticks: `4`",
        "- contracts_count: `18023`",
        "- accounts: `1`",
        "- subscribed_count: `5`",
        "- read_only: `true`",
        "- orders_sent_by_workflow: `0`",
        '- tick_counts_by_symbol: `{"AP888": 2, "RB888": 2}`',
        "- zero_tick_subscribed_symbols: `ZN888`",
        "",
    ]


def test_delayed_replay_section_lines_match_daily_brief_contract():
    summary = {
        "delayed_replay": {
            "available": False,
            "status": "pending",
            "valid_observation": False,
            "reason": "historical_db_lag",
            "latest_db_date": "2026-07-13",
            "missing_or_lagged_symbols": ["RB888", "ZN888"],
            "signals": 0,
            "trades": 0,
            "positions": 0,
            "risk_source": "replay_only",
        }
    }

    assert build_delayed_replay_section_lines(summary) == [
        "## 盘后 DB 延迟回放",
        "",
        "- delayed_replay.available: `false`",
        "- delayed_replay.status: `pending`",
        "- delayed_replay.valid_observation: `false`",
        "- delayed_replay.reason: `historical_db_lag`",
        "- latest_db_date: `2026-07-13`",
        "- missing_or_lagged_symbols: `RB888,ZN888`",
        "- replay_signals: `0`",
        "- replay_trades: `0`",
        "- replay_positions: `0`",
        "- risk_source: `replay_only`",
        "",
    ]


def test_threshold_diagnostics_section_lines_match_daily_brief_contract():
    summary = {
        "record": {
            "threshold_diagnostics": [
                {
                    "metric": "drawdown_abs_pct",
                    "level": "warning",
                    "value": 1.2992,
                    "warning": 1.1854,
                    "halt": 1.3171,
                    "warning_gap": 0.1138,
                    "halt_gap": -0.0179,
                    "unit": "%",
                },
                {
                    "metric": "consecutive_loss_abs_pct",
                    "level": "halt",
                    "value": 0.1218,
                    "warning": 0.0581,
                    "halt": 0.0646,
                    "warning_gap": 0.0637,
                    "halt_gap": 0.0572,
                    "unit": "%",
                },
            ]
        }
    }

    assert build_threshold_diagnostics_section_lines(summary) == [
        "## 阈值诊断",
        "",
        "- drawdown_abs_pct: `warning` (value=1.2992%, warning=1.1854%, halt=1.3171%, warning_gap=0.1138%, halt_gap=-0.0179%)",
        "- consecutive_loss_abs_pct: `halt` (value=0.1218%, warning=0.0581%, halt=0.0646%, warning_gap=0.0637%, halt_gap=0.0572%)",
        "",
    ]


def test_risk_source_breakdown_section_lines_show_consecutive_loss_streak():
    summary = {
        "risk_source_breakdown": {
            "consecutive_loss": {
                "available": True,
                "complete": True,
                "rows_available": True,
                "reason": "",
                "source": "delayed_replay.risk.consecutive_loss",
                "days": 3,
                "cumulative_return_pct": -0.1217590817,
                "abs_cumulative_return_pct": 0.1217590817,
                "start_date": "2026-07-22",
                "end_date": "2026-07-24",
                "rows": [
                    {"date": "2026-07-22", "daily_return_pct": -0.0401, "equity": 0.9996},
                    {"date": "2026-07-23", "daily_return_pct": -0.0502, "equity": 0.9991},
                    {"date": "2026-07-24", "daily_return_pct": -0.0314590817, "equity": 0.9988},
                ],
            },
        },
    }

    assert build_risk_source_breakdown_section_lines(summary) == [
        "## 风险来源拆解",
        "",
        "- consecutive_loss: `available=true`, complete=`true`, rows_available=`true`, reason=`无`, source=`delayed_replay.risk.consecutive_loss`, days=`3`, start=`2026-07-22`, end=`2026-07-24`, cumulative_return=`-0.1218%`, abs_cumulative_return=`0.1218%`",
        "- streak_rows:",
        "- 2026-07-22: daily_return=`-0.0401%`, equity=`0.9996`",
        "- 2026-07-23: daily_return=`-0.0502%`, equity=`0.9991`",
        "- 2026-07-24: daily_return=`-0.0315%`, equity=`0.9988`",
        "",
    ]


def test_risk_source_breakdown_section_lines_show_incomplete_legacy_rows():
    summary = {
        "risk_source_breakdown": {
            "consecutive_loss": {
                "available": True,
                "complete": False,
                "rows_available": False,
                "reason": "missing_consecutive_loss_rows",
                "source": "delayed_replay.risk.consecutive_loss",
                "days": 6,
                "cumulative_return_pct": -0.1217590817,
                "abs_cumulative_return_pct": 0.1217590817,
                "start_date": "",
                "end_date": "2023-06-28",
                "rows": [],
            },
        },
    }

    assert build_risk_source_breakdown_section_lines(summary) == [
        "## 风险来源拆解",
        "",
        "- consecutive_loss: `available=true`, complete=`false`, rows_available=`false`, reason=`missing_consecutive_loss_rows`, source=`delayed_replay.risk.consecutive_loss`, days=`6`, start=`无`, end=`2023-06-28`, cumulative_return=`-0.1218%`, abs_cumulative_return=`0.1218%`",
        "- streak_rows: `无`",
        "",
    ]

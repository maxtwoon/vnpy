"""Unit tests for the A37 Phase 0 exit-event reachability diagnostic."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from chan_strategy.positions import Event
from diagnostics.exit_event_reachability_report import (
    DEAD_SIGNAL_COUNT_KEY,
    DISCLAIMER,
    evaluate_exit_event_three_way,
    event_factors_match,
    event_signals_match,
    generate_exit_event_reachability_report,
)


def _event(
    name: str,
    operate: str,
    signals_any: list[str] | None = None,
    factors: list[dict] | None = None,
    signals_all: list[str] | None = None,
    signals_not: list[str] | None = None,
) -> Event:
    """Build an Event from a compact dict representation."""
    return Event.load({
        "name": name,
        "operate": operate,
        "signals_all": signals_all or [],
        "signals_any": signals_any or [],
        "signals_not": signals_not or [],
        "factors": factors or [],
    })


def test_event_signals_match_respects_all_any_not() -> None:
    """event_signals_match checks all/any/not gates exactly like Event.is_match."""
    event = _event(
        "e",
        "平多",
        signals_all=["TEST_K_A_x_任意_任意_0"],
        signals_any=["TEST_K_B_y_任意_任意_0", "TEST_K_B_z_任意_任意_0"],
        signals_not=["TEST_K_C_w_任意_任意_0"],
    )

    assert event_signals_match(event, {"TEST_K_A": "x_a_b_0", "TEST_K_B": "y_a_b_0"})
    assert not event_signals_match(event, {"TEST_K_A": "x_a_b_0", "TEST_K_B": "q_a_b_0"})
    assert not event_signals_match(event, {"TEST_K_A": "q_a_b_0", "TEST_K_B": "y_a_b_0"})
    assert not event_signals_match(
        event, {"TEST_K_A": "x_a_b_0", "TEST_K_B": "y_a_b_0", "TEST_K_C": "w_a_b_0"}
    )


def test_event_factors_match_requires_at_least_one_factor() -> None:
    """event_factors_match returns True iff a non-empty factor list matches."""
    event_with_factor = _event(
        "e",
        "平多",
        factors=[{
            "name": "f1",
            "signals_all": ["TEST_K_D_down_任意_任意_0"],
            "signals_any": [],
            "signals_not": [],
        }],
    )
    assert event_factors_match(event_with_factor, {"TEST_K_D": "down_a_b_0"})
    assert not event_factors_match(event_with_factor, {"TEST_K_D": "up_a_b_0"})

    event_no_factors = _event("e", "平多")
    assert not event_no_factors.factors
    assert not event_factors_match(event_no_factors, {"TEST_K_D": "down_a_b_0"})


def test_evaluate_three_way_legacy_fired_requires_both_gates() -> None:
    """legacy_fired only when signals and factors both match."""
    event = _event(
        "e",
        "平多",
        signals_any=["TEST_K_R_结构失效_任意_任意_0"],
        factors=[{
            "name": "direction",
            "signals_all": ["TEST_K_DIR_down_任意_任意_0"],
            "signals_any": ["TEST_K_POS_below_任意_任意_0", "TEST_K_POS_inside_任意_任意_0"],
            "signals_not": [],
        }],
    )

    # Both gates satisfied -> legacy fires.
    signals = {
        "TEST_K_R": "结构失效_任意_任意_95",
        "TEST_K_DIR": "down_任意_任意_50",
        "TEST_K_POS": "below_任意_任意_30",
    }
    result = evaluate_exit_event_three_way(event, signals)
    assert result["legacy_fired"] is True
    assert result["struct_alone"] is False
    assert result["factor_alone"] is False

    # Only event-level signal satisfied -> struct_alone.
    signals_struct_only = {
        "TEST_K_R": "结构失效_任意_任意_95",
        "TEST_K_DIR": "up_任意_任意_50",
        "TEST_K_POS": "above_任意_任意_70",
    }
    result = evaluate_exit_event_three_way(event, signals_struct_only)
    assert result["legacy_fired"] is False
    assert result["struct_alone"] is True
    assert result["factor_alone"] is False

    # Only factor satisfied -> factor_alone.
    signals_factor_only = {
        "TEST_K_R": "结构完好_任意_任意_0",
        "TEST_K_DIR": "down_任意_任意_50",
        "TEST_K_POS": "below_任意_任意_30",
    }
    result = evaluate_exit_event_three_way(event, signals_factor_only)
    assert result["legacy_fired"] is False
    assert result["struct_alone"] is False
    assert result["factor_alone"] is True

    # Neither satisfied -> none.
    signals_none = {
        "TEST_K_R": "结构完好_任意_任意_0",
        "TEST_K_DIR": "up_任意_任意_50",
        "TEST_K_POS": "above_任意_任意_70",
    }
    result = evaluate_exit_event_three_way(event, signals_none)
    assert result["legacy_fired"] is False
    assert result["struct_alone"] is False
    assert result["factor_alone"] is False


def test_three_way_counts_are_mutually_exclusive_per_bar() -> None:
    """For a single evaluation, at most one of the three booleans is True."""
    event = _event(
        "e",
        "平多",
        signals_any=["TEST_K_R_结构失效_任意_任意_0"],
        factors=[{
            "name": "direction",
            "signals_all": ["TEST_K_DIR_down_任意_任意_0"],
            "signals_any": [],
            "signals_not": [],
        }],
    )

    cases = [
        {"TEST_K_R": "结构失效_任意_任意_95", "TEST_K_DIR": "down_任意_任意_50"},
        {"TEST_K_R": "结构失效_任意_任意_95", "TEST_K_DIR": "up_任意_任意_50"},
        {"TEST_K_R": "结构完好_任意_任意_0", "TEST_K_DIR": "down_任意_任意_50"},
        {"TEST_K_R": "结构完好_任意_任意_0", "TEST_K_DIR": "up_任意_任意_50"},
    ]
    for signals in cases:
        result = evaluate_exit_event_three_way(event, signals)
        true_count = sum(1 for v in result.values() if v)
        assert true_count <= 1


def _make_memory_db_with_bars(tmp_path: Path, symbol: str = "TEST") -> Path:
    """Create a small in-memory SQLite DB with a 1-minute raw table."""
    db = tmp_path / "bars.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE test_1m_raw ("
        "datetime TEXT, symbol TEXT, open REAL, high REAL, "
        "low REAL, close REAL, volume REAL, amount REAL"
        ")"
    )
    base = "2024-01-02 09:00:00"
    rows = [
        (f"2024-01-02 09:{i:02d}:00", symbol, 100.0, 101.0, 99.0, 100.0 + i * 0.01, 1000.0, 100000.0)
        for i in range(10)
    ]
    conn.executemany("INSERT INTO test_1m_raw VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def test_missing_db_marks_all_symbols_unavailable(tmp_path: Path) -> None:
    """A missing DB must produce unavailable status for every symbol."""
    missing_db = tmp_path / "does_not_exist.db"
    json_path, md_path, report = generate_exit_event_reachability_report(
        db_path=missing_db,
        symbols=["TEST1", "TEST2"],
        start_date="2024-01-01",
        end_date="2024-01-03",
        output_dir=tmp_path,
        warmup_bars=100,
    )

    assert json_path.exists()
    assert md_path.exists()

    for symbol, result in report["symbol_results"].items():
        assert result["status"] == "unavailable"
        assert "resolved DB does not exist" in result["reason"]


def test_no_bars_marks_symbol_unavailable(tmp_path: Path) -> None:
    """A DB with a matching table but no rows for the symbol must be unavailable."""
    db = _make_memory_db_with_bars(tmp_path, symbol="OTHER")
    json_path, md_path, report = generate_exit_event_reachability_report(
        db_path=db,
        symbols=["TEST"],
        start_date="2024-01-01",
        end_date="2024-01-03",
        output_dir=tmp_path,
        warmup_bars=100,
    )

    assert json_path.exists()
    assert md_path.exists()
    assert report["symbol_results"]["TEST"]["status"] == "unavailable"
    assert "no 1-minute bars loaded" in report["symbol_results"]["TEST"]["reason"]


def test_json_output_schema_and_disclaimer(tmp_path: Path) -> None:
    """The JSON report must carry the disclaimer and required schema keys."""
    missing_db = tmp_path / "missing.db"
    json_path, _, report = generate_exit_event_reachability_report(
        db_path=missing_db,
        symbols=["TEST"],
        start_date="2024-01-01",
        end_date="2024-01-03",
        output_dir=tmp_path,
        warmup_bars=100,
    )

    raw = json_path.read_text(encoding="utf-8")
    assert DISCLAIMER in raw
    assert "GOAL PASSED" not in raw

    assert report["disclaimer"] == DISCLAIMER
    assert "generated_at" in report
    assert "parameters" in report
    assert "summary" in report
    assert "symbol_results" in report

    summary = report["summary"]
    assert "total_legacy_fired" in summary
    assert "total_struct_alone" in summary
    assert "total_factor_alone" in summary
    assert "dead_signal_counts" in summary
    assert DEAD_SIGNAL_COUNT_KEY in summary["dead_signal_counts"]


def test_markdown_output_schema_and_no_goal_passed(tmp_path: Path) -> None:
    """The Markdown report must carry the disclaimer and never claim GOAL PASSED."""
    missing_db = tmp_path / "missing.db"
    _, md_path, _ = generate_exit_event_reachability_report(
        db_path=missing_db,
        symbols=["TEST"],
        start_date="2024-01-01",
        end_date="2024-01-03",
        output_dir=tmp_path,
        warmup_bars=100,
    )

    raw = md_path.read_text(encoding="utf-8")
    assert "# Exit-Event Reachability Report" in raw
    assert DISCLAIMER in raw
    assert "legacy_fired" in raw
    assert "struct_alone" in raw
    assert "factor_alone" in raw
    assert "GOAL PASSED" not in raw


def test_source_code_contains_no_trading_interface_tokens() -> None:
    """The diagnostic script must not import or invoke trading interfaces."""
    root = Path(__file__).resolve().parents[2]
    source_path = root / "diagnostics" / "exit_event_reachability_report.py"
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = [
        "send_order",
        "cancel_order",
        "buy(",
        "sell(",
        "short(",
        "cover(",
    ]
    for token in forbidden_tokens:
        assert token not in source, f"Forbidden trading-interface token found: {token}"


def test_generate_report_with_existing_db_but_insufficient_bars(tmp_path: Path) -> None:
    """A DB with a few bars but insufficient warmup must be marked unavailable."""
    db = _make_memory_db_with_bars(tmp_path, symbol="TEST")
    _, _, report = generate_exit_event_reachability_report(
        db_path=db,
        symbols=["TEST"],
        start_date="2024-01-01",
        end_date="2024-01-03",
        output_dir=tmp_path,
        warmup_bars=100,
    )

    result = report["symbol_results"]["TEST"]
    assert result["status"] == "unavailable"
    assert "insufficient" in result["reason"]

import sys
import sqlite3
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from chan_strategy.config import STRATEGY_CONFIG  # noqa: E402
from diagnostics.backtest_matrix_report import (  # noqa: E402
    _dominant_symbol,
    write_markdown,
)


def _minimal_matrix() -> dict:
    return {
        "generated_at": "2024-01-01T00:00:00+00:00",
        "db_path": "/tmp/test.db",
        "symbols": {"TEST": {}},
        "checks": {"TEST": {}},
    }


def test_write_markdown_includes_research_caveat_and_banner(tmp_path: Path) -> None:
    saved = STRATEGY_CONFIG.get("sizing_model", "research")
    STRATEGY_CONFIG["sizing_model"] = "research"
    try:
        path = tmp_path / "report.md"
        write_markdown(_minimal_matrix(), path)
        text = path.read_text(encoding="utf-8")
        assert "RESEARCH ONLY" in text
        assert "RESEARCH-ONLY / NOT PROMOTION EVIDENCE" in text
        assert "当前仓位模型为 `research`" in text
        assert "不是真实资金 P&L 曲线" in text
        assert "当前仓位模型为 `risk`" not in text
    finally:
        STRATEGY_CONFIG["sizing_model"] = saved


def test_write_markdown_includes_risk_caveat_and_banner(tmp_path: Path) -> None:
    saved = STRATEGY_CONFIG.get("sizing_model", "research")
    STRATEGY_CONFIG["sizing_model"] = "risk"
    try:
        path = tmp_path / "report.md"
        write_markdown(_minimal_matrix(), path)
        text = path.read_text(encoding="utf-8")
        assert "RESEARCH ONLY" in text
        assert "RESEARCH-ONLY / NOT PROMOTION EVIDENCE" in text
        assert "当前仓位模型为 `risk`" in text
        assert "未经验证于实盘" in text
        assert "不是真实资金 P&L 曲线" not in text
    finally:
        STRATEGY_CONFIG["sizing_model"] = saved


def _make_db(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    db = tmp_path / "mixed.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table ap888_1M_raw ("
        "datetime text, symbol text, open real, high real, low real, close real, volume real, amount real"
        ")"
    )
    typed_rows = [
        (dt, sym, 100.0, 101.0, 99.0, 100.0, 1.0, 1.0)
        for dt, sym in rows
    ]
    conn.executemany(
        "insert into ap888_1M_raw values (?,?,?,?,?,?,?,?)",
        typed_rows,
    )
    conn.commit()
    conn.close()
    return db


def test_dominant_symbol_prefers_symbol_that_covers_end_date(tmp_path: Path) -> None:
    """When one symbol stops before the target date, choose the one that reaches it."""
    rows = [
        # Older uppercase series: more rows but ends before 2026-07-06.
        (f"2022-01-04 09:{i:02d}:00", "AP888") for i in range(60)
    ] + [
        # Newer lowercase series: fewer rows but covers 2026-07-06.
        (f"2026-07-06 09:{i:02d}:00", "ap888") for i in range(30)
    ]
    db = _make_db(tmp_path, rows)
    assert _dominant_symbol(db, "ap888_1M_raw", "2022-01-01", "2026-07-06") == "ap888"


def test_dominant_symbol_falls_back_to_latest_bar_when_none_cover_end(tmp_path: Path) -> None:
    """If no symbol reaches the end date, pick the one with the latest bar."""
    rows = [
        (f"2022-01-04 09:{i:02d}:00", "AP888") for i in range(60)
    ] + [
        (f"2026-06-30 09:{i:02d}:00", "ap888") for i in range(10)
    ]
    db = _make_db(tmp_path, rows)
    assert _dominant_symbol(db, "ap888_1M_raw", "2022-01-01", "2026-07-06") == "ap888"


def test_dominant_symbol_returns_only_symbol_when_single_series(tmp_path: Path) -> None:
    rows = [
        (f"2026-07-06 09:{i:02d}:00", "rb888") for i in range(10)
    ]
    db = _make_db(tmp_path, rows)
    assert _dominant_symbol(db, "ap888_1M_raw", "2022-01-01", "2026-07-06") == "rb888"

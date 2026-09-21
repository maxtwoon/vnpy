"""Storage boundaries, provenance and real file round trips."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from vnpy_datasource.storage import MANIFEST_NAME, save_history


def history(*, adjustment: str = "none", turnover: float | None = 12345.0) -> dict:
    return {
        "status": "ok", "source": "fixture", "recipe": "daily", "kind": "bars",
        "records": [{
            "datetime": "2025-01-02", "open": 1.1, "high": 1.3,
            "low": 1.0, "close": 1.2, "volume": 10000.0, "turnover": turnover,
        }],
        "metadata": {
            "interval": "d", "adjustment": adjustment, "time_label": "date",
            "volume_unit": "shares", "turnover_unit": "CNY",
            "missing_fields": ["turnover"] if turnover is None else [],
        },
        "request": {"symbol": "159915.SZSE"}, "attempts": [],
        "fetched_at": "2025-01-03T01:00:00Z", "registry_sha256": "fixture-hash",
    }


def test_sqlite_roundtrip_and_adapter_tables(tmp_path: Path) -> None:
    payload = history()
    original = copy.deepcopy(payload)
    result = save_history(payload, "159915.SZSE", "sqlite", tmp_path / "research")
    assert result["verified_rows"] == 1
    with sqlite3.connect(result["path"]) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"dbbardata", "dbbaroverview", "dbtickdata", "dbtickoverview"} <= tables
        assert connection.execute("SELECT symbol, exchange, close_price, turnover FROM dbbardata").fetchone() == (
            "159915", "SZSE", 1.2, 12345.0,
        )
        assert connection.execute("SELECT count FROM dbbaroverview").fetchone() == (1,)
    receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
    assert receipt["storage_status"] == "verified"
    assert receipt["source"] == "fixture"
    assert payload == original


def test_missing_turnover_is_explicit_in_receipt(tmp_path: Path) -> None:
    result = save_history(history(turnover=None), "159915.SZSE", "sqlite", tmp_path)
    receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
    assert receipt["turnover_missing"] is True
    assert receipt["turnover_missing_at"] == ["2025-01-02"]
    assert receipt["turnover_placeholder"] == 0.0
    assert receipt["metadata"]["missing_fields"] == ["turnover"]
    with sqlite3.connect(result["path"]) as connection:
        assert connection.execute("SELECT turnover FROM dbbardata").fetchone() == (0.0,)


def test_adjustment_cannot_change_existing_output(tmp_path: Path) -> None:
    result = save_history(history(), "159915.SZSE", "sqlite", tmp_path)
    before = Path(result["path"]).read_bytes()
    with pytest.raises(ValueError, match="different target or adjustment"):
        save_history(history(adjustment="qfq"), "159915.SZSE", "sqlite", tmp_path)
    assert Path(result["path"]).read_bytes() == before


def test_unmanaged_directory_is_never_adopted(tmp_path: Path) -> None:
    protected = tmp_path / "database.db"
    protected.write_bytes(b"existing researcher database")
    with pytest.raises(ValueError, match="unmanaged"):
        save_history(history(), "159915.SZSE", "sqlite", tmp_path)
    assert protected.read_bytes() == b"existing researcher database"
    assert not (tmp_path / MANIFEST_NAME).exists()


def test_overlapping_query_is_idempotent(tmp_path: Path) -> None:
    first = save_history(history(), "159915.SZSE", "sqlite", tmp_path)
    second = save_history(history(), "159915.SZSE", "sqlite", tmp_path)
    assert first["receipt"] != second["receipt"]
    with sqlite3.connect(first["path"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dbbardata").fetchone() == (1,)


def test_failed_source_cannot_write(tmp_path: Path) -> None:
    payload = history()
    payload["status"] = "source_unavailable"
    with pytest.raises(ValueError, match="Cannot store"):
        save_history(payload, "159915.SZSE", "sqlite", tmp_path / "uncreated")
    assert not (tmp_path / "uncreated").exists()


def test_alpha_parquet_roundtrip(tmp_path: Path) -> None:
    pl = pytest.importorskip("polars")
    result = save_history(history(), "159915.SZSE", "alpha", tmp_path)
    frame = pl.read_parquet(result["path"])
    assert frame["close"].to_list() == [1.2]
    assert frame["volume"].to_list() == [10000.0]
    assert result["format"] == "AlphaLab"
    assert result["verified_rows"] == 1


def test_cli_stdout_is_one_json_object(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from vnpy_datasource import cli

    class Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def describe(self) -> dict:
            print("provider progress belongs on stderr")
            return {"runtime_ready": True}

    monkeypatch.setattr(cli, "DataSourceClient", Client)
    assert cli.main(["capabilities"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"runtime_ready": True}
    assert "progress" in captured.err


def test_cli_no_data_does_not_create_download_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from vnpy_datasource import cli

    class Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def history(self, **kwargs: object) -> dict:
            return {"status": "no_data", "records": []}

    monkeypatch.setattr(cli, "DataSourceClient", Client)
    output = tmp_path / "not-created"
    code = cli.main([
        "download", "--symbol", "159915.SZSE", "--start", "2025-01-01",
        "--end", "2025-01-02", "--target", "sqlite", "--output", str(output),
    ])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "no_data"
    assert not output.exists()


def test_cli_json_export_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from vnpy_datasource import cli

    class Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def describe(self) -> dict:
            return {"runtime_ready": True}

    monkeypatch.setattr(cli, "DataSourceClient", Client)
    protected = tmp_path / "existing.json"
    protected.write_text("original", encoding="utf-8")
    assert cli.main(["capabilities", "--output", str(protected)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    assert protected.read_text(encoding="utf-8") == "original"

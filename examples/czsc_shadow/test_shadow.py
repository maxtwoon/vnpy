"""Consumer regressions using real BarData and the public timing engine."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("vnpy_shadow_runner", HERE / "run.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def rows() -> list[dict[str, Any]]:
    start = datetime.fromisoformat("2025-01-02T09:30:00+08:00")
    return [dict(symbol="IF2501.CFFEX", datetime=(start + timedelta(minutes=i)).isoformat(),
                 interval="1m", closed=True, open_price=100, high_price=101,
                 low_price=99, close_price=100, volume=1, turnover=100,
                 open_interest=88) for i in range(35)]


def execute(tmp_path: Path, data: list[dict[str, Any]], name: str = "result") -> dict[str, Any]:
    source = tmp_path / "input.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in data), encoding="utf-8")
    config = tmp_path / "synthetic.toml"
    config.write_text((HERE / "futures.toml").read_text(encoding="utf-8").replace(
        "warmup_1m_bars = 20000", "warmup_1m_bars = 1"
    ), encoding="utf-8")
    return runner.replay(source, config, tmp_path / name,
                         czsc_root=Path("D:/repo/czsc-timing-engine"), symbol="IF2501.CFFEX",
                         snapshot_id="synthetic-engineering-fixture-v1", bar_label="open",
                         as_of=datetime.fromisoformat("2025-01-02T10:05:00+08:00"))


def test_real_engine_replay_is_deterministic_and_input_unchanged(tmp_path: Path) -> None:
    first = execute(tmp_path, rows())
    original_hash = runner.digest(tmp_path / "input.jsonl")
    second = execute(tmp_path, rows(), "repeat")
    assert first["status"] == second["status"] == "ok"
    assert first["rows"] == 35 and first["policy_id"] == "passthrough"
    assert first["decisions"] > 0
    assert original_hash == runner.digest(tmp_path / "input.jsonl")
    assert (tmp_path / "result/decisions.jsonl").read_bytes() == (tmp_path / "repeat/decisions.jsonl").read_bytes()
    assert first["performance_claim"] == "none"


@pytest.mark.parametrize("case", ["duplicate", "unclosed", "future", "wrong_symbol", "missing_amount"])
def test_bad_input_fails_visibly(tmp_path: Path, case: str) -> None:
    data = rows()
    if case == "duplicate":
        data[1] = dict(data[0])
    elif case == "unclosed":
        data[0]["closed"] = False
    elif case == "future":
        data[-1]["datetime"] = "2025-01-02T10:05:00+08:00"
    elif case == "wrong_symbol":
        data[0]["symbol"] = "IF2502.CFFEX"
    else:
        del data[0]["turnover"]
    with pytest.raises((ValueError, KeyError)):
        execute(tmp_path, data)
    report = json.loads((tmp_path / "result/result.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"


def test_existing_output_refused(tmp_path: Path) -> None:
    execute(tmp_path, rows())
    before = (tmp_path / "result/result.json").read_bytes()
    with pytest.raises(FileExistsError):
        execute(tmp_path, rows())
    assert (tmp_path / "result/result.json").read_bytes() == before

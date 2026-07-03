from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_SYMBOLS = ["RB888", "SC888", "AP888", "A888", "ZN888"]


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AssertionError(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_symbols(actual: set[str], source: str) -> None:
    missing = [s for s in REQUIRED_SYMBOLS if s not in actual]
    if missing:
        raise AssertionError(f"{source} missing symbols: {missing}")


def _check_report(report: dict[str, Any], source: str) -> None:
    if "error" in report:
        raise AssertionError(f"{source} has error: {report['error']}")
    if int(report.get("total_trades", 0)) <= 0:
        raise AssertionError(f"{source} has no trades")
    if float(report.get("final_equity", 0)) <= 0:
        raise AssertionError(f"{source} final_equity <= 0")


def check_execution_matrix(path: Path) -> list[str]:
    data = _load(path)
    checked: list[str] = []
    for period_name, period in data["periods"].items():
        for scenario_name, scenario in period["scenarios"].items():
            symbols = set(scenario["symbols"].keys())
            _assert_symbols(symbols, f"{path.name}:{period_name}:{scenario_name}")
            if int(scenario["combo"].get("errors", 0)) != 0:
                raise AssertionError(f"{path.name}:{period_name}:{scenario_name} combo errors != 0")
            for symbol in REQUIRED_SYMBOLS:
                _check_report(
                    scenario["symbols"][symbol],
                    f"{path.name}:{period_name}:{scenario_name}:{symbol}",
                )
                checked.append(f"{period_name}/{scenario_name}/{symbol}")
    return checked


def check_rolling_matrix(path: Path) -> list[str]:
    data = _load(path)
    checked: list[str] = []
    for window_name, window in data["windows"].items():
        for scenario_name, scenario in window["scenarios"].items():
            symbols = set(scenario["symbols"].keys())
            _assert_symbols(symbols, f"{path.name}:{window_name}:{scenario_name}")
            if int(scenario["combo"].get("errors", 0)) != 0:
                raise AssertionError(f"{path.name}:{window_name}:{scenario_name} combo errors != 0")
            for symbol in REQUIRED_SYMBOLS:
                _check_report(
                    scenario["symbols"][symbol],
                    f"{path.name}:{window_name}:{scenario_name}:{symbol}",
                )
                checked.append(f"{window_name}/{scenario_name}/{symbol}")
    return checked


def check_trade_attribution(path: Path) -> list[str]:
    data = _load(path)
    checked: list[str] = []
    for period_name, period in data["periods"].items():
        symbols = set(k for k in period["symbols"] if not k.startswith("_"))
        _assert_symbols(symbols, f"{path.name}:{period_name}")
        for symbol in REQUIRED_SYMBOLS:
            row = period["symbols"][symbol]
            if int(row["baseline_stats"].get("trades", 0)) <= 0:
                raise AssertionError(f"{path.name}:{period_name}:{symbol} baseline has no trades")
            if int(row["combined_stats"].get("trades", 0)) <= 0:
                raise AssertionError(f"{path.name}:{period_name}:{symbol} combined has no trades")
            checked.append(f"{period_name}/{symbol}")
    return checked


def main() -> None:
    parser = argparse.ArgumentParser(description="Check five-symbol diagnostics acceptance.")
    parser.add_argument(
        "--execution-json",
        type=Path,
        default=Path(__file__).with_name("strategy_execution_experiment_matrix.json"),
    )
    parser.add_argument(
        "--rolling-json",
        type=Path,
        default=Path(__file__).with_name("rolling_candidate_matrix.json"),
    )
    parser.add_argument(
        "--attribution-json",
        type=Path,
        default=Path(__file__).with_name("trade_difference_attribution.json"),
    )
    args = parser.parse_args()

    execution = check_execution_matrix(args.execution_json)
    rolling = check_rolling_matrix(args.rolling_json)
    attribution = check_trade_attribution(args.attribution_json)

    print("five-symbol acceptance passed")
    print(f"symbols={','.join(REQUIRED_SYMBOLS)}")
    print(f"execution_checks={len(execution)}")
    print(f"rolling_checks={len(rolling)}")
    print(f"attribution_checks={len(attribution)}")


if __name__ == "__main__":
    main()

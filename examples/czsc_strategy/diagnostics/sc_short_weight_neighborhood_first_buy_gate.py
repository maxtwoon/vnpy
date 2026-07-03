from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent

from sc_short_weight_neighborhood import MULTIPLIERS, params_for_multiplier, write_markdown  # noqa: E402
from portfolio_goal_evaluator import (  # noqa: E402
    GOAL,
    _goal_status,
    _json_safe,
    _walk_forward,
    _evaluate_period,
    OOS_START,
    OOS_END,
)
from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS  # noqa: E402


def build_report(db_path: Path, symbols: list[str], first_buy_gate: dict[str, Any]) -> dict[str, Any]:
    import portfolio_goal_evaluator as evaluator

    original_scenario_params = evaluator._scenario_params
    payload = {"goal": GOAL, "first_buy_gate": first_buy_gate, "multipliers": {}}
    try:
        for multiplier in MULTIPLIERS:
            scenario = f"sc_short_{multiplier:g}_first_buy_gate"

            def scenario_params(name: str, symbol: str, m: float = multiplier) -> dict[str, Any]:
                if name == scenario:
                    params = params_for_multiplier(m, symbol)
                    params.update(first_buy_gate)
                    return params
                return original_scenario_params(name, symbol)

            evaluator._scenario_params = scenario_params
            oos = _evaluate_period(db_path, symbols, OOS_START, OOS_END, scenario)
            wf = _walk_forward(db_path, symbols, scenario)
            payload["multipliers"][str(multiplier)] = {
                "scenario": scenario,
                "pos_1sell": 0.10 * multiplier,
                "pos_3sell": 0.30 * multiplier,
                "out_sample": oos,
                "walk_forward": wf,
                "goal_status": _goal_status(oos, wf),
            }
    finally:
        evaluator._scenario_params = original_scenario_params
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SC short multiplier neighborhood with first-buy research gate.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--gate", choices=["block_daily_down"], default="block_daily_down")
    parser.add_argument("--out-json", type=Path, default=HERE / "sc_short_weight_neighborhood_first_buy_gate.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "sc_short_weight_neighborhood_first_buy_gate.md")
    args = parser.parse_args()

    gates = {
        "block_daily_down": {"block_1buy_daily_down": True},
    }
    payload = build_report(args.db_path, args.symbols, gates[args.gate])
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

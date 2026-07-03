from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio_goal_evaluator import (
    GOAL,
    _fmt_num,
    _fmt_pct,
    _goal_status,
    _json_safe,
    _walk_forward,
    _evaluate_period,
    OOS_START,
    OOS_END,
)
from chan_strategy.config import SQLITE_DB_PATH
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS
from diagnostics.strategy_execution_experiment_matrix import SECOND_BUY_FILTERS, TRAILING_OVERRIDES


MULTIPLIERS = [0.75, 0.80, 0.847, 0.85, 0.90, 1.00]


def params_for_multiplier(multiplier: float, symbol: str) -> dict[str, Any]:
    params = copy.deepcopy(SECOND_BUY_FILTERS)
    params.update(copy.deepcopy(TRAILING_OVERRIDES))
    if symbol in {"AP888", "A888"}:
        params["max_2buy_entry_vs_anchor_pct"] = None
    params["enable_short"] = True
    params["enable_short_symbols"] = ["SC888"]
    params["pos_1sell"] = 0.10 * multiplier
    params["pos_3sell"] = 0.30 * multiplier
    return params


def build_report(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    import portfolio_goal_evaluator as evaluator

    original_scenario_params = evaluator._scenario_params
    payload = {"goal": GOAL, "multipliers": {}}
    try:
        for multiplier in MULTIPLIERS:
            scenario = f"sc_short_{multiplier:g}"

            def scenario_params(name: str, symbol: str, m: float = multiplier) -> dict[str, Any]:
                if name == scenario:
                    return params_for_multiplier(m, symbol)
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


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# SC Short Weight Neighborhood",
        "",
        "| multiplier | pass | trades | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for multiplier, row in payload["multipliers"].items():
        m = row["out_sample"]["metrics"]
        bh = row["out_sample"]["buy_hold"]
        wf = row["walk_forward"]
        lines.append(
            f"| {multiplier} | {row['goal_status']['passed']} | {_fmt_num(m['trades'], 0)} | "
            f"{_fmt_num(m['profit_factor'])} | {_fmt_pct(m['max_drawdown_pct'])} | "
            f"{_fmt_num(m['sharpe'])} | {_fmt_num(m['calmar'])} | "
            f"{wf['positive_windows']}/{wf['total_windows']} | {_fmt_num(bh['sharpe'])} | {_fmt_num(bh['calmar'])} |"
        )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate neighborhood around SC short position multiplier.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("sc_short_weight_neighborhood.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("sc_short_weight_neighborhood.md"))
    args = parser.parse_args()

    payload = build_report(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

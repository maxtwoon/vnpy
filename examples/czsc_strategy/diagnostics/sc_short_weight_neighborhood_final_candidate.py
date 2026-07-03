from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS  # noqa: E402
from portfolio_goal_evaluator import (  # noqa: E402
    GOAL,
    _evaluate_period,
    _fmt_num,
    _fmt_pct,
    _goal_status,
    _json_safe,
    _walk_forward,
    OOS_END,
    OOS_START,
)
from platform_final_candidate import CANDIDATE_NAME, FINAL_SC_MULTIPLIERS, final_candidate_params  # noqa: E402


def build_report(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    import portfolio_goal_evaluator as evaluator

    original = evaluator._scenario_params
    payload = {"goal": GOAL, "candidate": CANDIDATE_NAME, "multipliers": {}}
    try:
        for multiplier in FINAL_SC_MULTIPLIERS:
            scenario = f"final_sc_short_{multiplier:g}"

            def scenario_params(name: str, symbol: str, m: float = multiplier) -> dict[str, Any]:
                if name == scenario:
                    return final_candidate_params(m, symbol)
                return original(name, symbol)

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
        evaluator._scenario_params = original
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Final Candidate SC Short Weight Neighborhood",
        "",
        f"- candidate: `{payload['candidate']}`",
        "",
        "| multiplier | pass | trades | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for multiplier, row in payload["multipliers"].items():
        metrics = row["out_sample"]["metrics"]
        bh = row["out_sample"]["buy_hold"]
        wf = row["walk_forward"]
        lines.append(
            f"| {multiplier} | {row['goal_status']['passed']} | {_fmt_num(metrics['trades'], 0)} | "
            f"{_fmt_num(metrics['profit_factor'])} | {_fmt_pct(metrics['max_drawdown_pct'])} | "
            f"{_fmt_num(metrics['sharpe'])} | {_fmt_num(metrics['calmar'])} | "
            f"{wf['positive_windows']}/{wf['total_windows']} | {_fmt_num(bh['sharpe'])} | {_fmt_num(bh['calmar'])} |"
        )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SC short neighborhood for the final platform candidate.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=HERE / "sc_short_weight_neighborhood_final_candidate.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "sc_short_weight_neighborhood_final_candidate.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

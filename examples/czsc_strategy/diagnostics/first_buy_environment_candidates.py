from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent

from portfolio_goal_evaluator import (  # noqa: E402
    _fmt_num,
    _fmt_pct,
    _goal_status,
    _json_safe,
    _walk_forward,
    _evaluate_period,
    OOS_START,
    OOS_END,
)
from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from sc_short_weight_neighborhood import params_for_multiplier  # noqa: E402
from symbol_set_stability_scan import SYMBOL_SETS, _scaled_goal_status  # noqa: E402


CANDIDATES = {
    "current": {},
    "block_daily_down": {"block_1buy_daily_down": True},
    "block_daily_not_up": {"block_1buy_daily_not_up": True},
    "longs_AP_A_ZN": {"enable_1buy_symbols": ["AP888", "A888", "ZN888"]},
    "longs_A_ZN": {"enable_1buy_symbols": ["A888", "ZN888"]},
}

DEFAULT_SYMBOL_SET_NAMES = ["all5", "no_SC", "core_AP_A_ZN"]


def _patch_evaluator(candidate: dict[str, Any], multiplier: float):
    import portfolio_goal_evaluator as evaluator

    original = evaluator._scenario_params
    scenario = "candidate"

    def scenario_params(name: str, symbol: str) -> dict[str, Any]:
        if name != scenario:
            return original(name, symbol)
        params = params_for_multiplier(multiplier, symbol)
        params.update(copy.deepcopy(candidate))
        return params

    evaluator._scenario_params = scenario_params
    return evaluator, original, scenario


def _evaluate_candidate(
    db_path: Path,
    name: str,
    candidate: dict[str, Any],
    multiplier: float,
    symbol_set_names: list[str],
) -> dict[str, Any]:
    evaluator, original, scenario = _patch_evaluator(candidate, multiplier)
    try:
        all5 = _evaluate_period(db_path, SYMBOL_SETS["all5"], OOS_START, OOS_END, scenario)
        wf = _walk_forward(db_path, SYMBOL_SETS["all5"], scenario)
        symbol_sets = {}
        for set_name in symbol_set_names:
            symbols = SYMBOL_SETS[set_name]
            oos = _evaluate_period(db_path, symbols, OOS_START, OOS_END, scenario)
            swf = _walk_forward(db_path, symbols, scenario)
            symbol_sets[set_name] = {
                "symbols": symbols,
                "out_sample": oos,
                "walk_forward": swf,
                "goal_status": _scaled_goal_status(oos, swf, len(symbols)),
            }
        pass_count = sum(1 for row in symbol_sets.values() if row["goal_status"]["passed"])
        return {
            "candidate": name,
            "params": copy.deepcopy(candidate),
            "multiplier": multiplier,
            "all5": {
                "out_sample": all5,
                "walk_forward": wf,
                "goal_status": _goal_status(all5, wf),
            },
            "symbol_sets": symbol_sets,
            "symbol_set_pass_count": pass_count,
            "symbol_set_total": len(symbol_sets),
            "symbol_set_pass_ratio": pass_count / len(symbol_sets) if symbol_sets else 0.0,
        }
    finally:
        evaluator._scenario_params = original


def build_report(
    db_path: Path,
    multiplier: float,
    candidates: list[str],
    symbol_set_names: list[str],
) -> dict[str, Any]:
    rows = {}
    for name in candidates:
        rows[name] = _evaluate_candidate(db_path, name, CANDIDATES[name], multiplier, symbol_set_names)
    return {"multiplier": multiplier, "symbol_sets": symbol_set_names, "rows": rows}


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# First-Buy Environment Candidates",
        "",
        f"- SC short multiplier: `{payload['multiplier']}`",
        "- Goal: reduce weak-window first-buy damage without creating a narrow single-point fix.",
        "",
        "| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in payload["rows"].items():
        m = row["all5"]["out_sample"]["metrics"]
        wf = row["all5"]["walk_forward"]
        failing_sets = [s for s, item in row["symbol_sets"].items() if not item["goal_status"]["passed"]]
        lines.append(
            f"| {name} | {row['all5']['goal_status']['passed']} | "
            f"{row['symbol_set_pass_count']}/{row['symbol_set_total']} | "
            f"{_fmt_num(m['trades'], 0)} | {_fmt_num(m['profit_factor'])} | "
            f"{_fmt_pct(m['max_drawdown_pct'])} | {_fmt_num(m['sharpe'])} | "
            f"{_fmt_num(m['calmar'])} | {wf['positive_windows']}/{wf['total_windows']} | "
            f"{', '.join(failing_sets) or '-'} |"
        )
    lines.extend(["", "## Symbol-Set Detail", ""])
    for name, row in payload["rows"].items():
        lines.extend([
            f"### {name}",
            "",
            "| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ])
        for set_name, item in row["symbol_sets"].items():
            m = item["out_sample"]["metrics"]
            wf = item["walk_forward"]
            fails = [k for k, v in item["goal_status"]["checks"].items() if not v]
            lines.append(
                f"| {set_name} | {item['goal_status']['passed']} | "
                f"{_fmt_num(m['trades'], 0)} | {_fmt_num(m['profit_factor'])} | "
                f"{_fmt_num(m['sharpe'])} | {_fmt_num(m['calmar'])} | "
                f"{wf['positive_windows']}/{wf['total_windows']} | {', '.join(fails) or '-'} |"
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan first-buy environment gates for platform robustness.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--multiplier", type=float, default=0.847)
    parser.add_argument("--candidates", nargs="+", default=["current", "block_daily_down"])
    parser.add_argument("--sets", nargs="+", default=DEFAULT_SYMBOL_SET_NAMES, choices=sorted(SYMBOL_SETS))
    parser.add_argument("--out-json", type=Path, default=HERE / "first_buy_environment_candidates.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "first_buy_environment_candidates.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, args.multiplier, args.candidates, args.sets)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

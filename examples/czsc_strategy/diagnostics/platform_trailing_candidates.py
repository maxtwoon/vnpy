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
from diagnostics.rolling_candidate_matrix import WINDOWS  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from sc_short_weight_neighborhood import params_for_multiplier  # noqa: E402
from symbol_set_stability_scan import SYMBOL_SETS, _scaled_goal_status  # noqa: E402


def _trailing(symbols: list[str], start_bp: int, drawback_pct: float) -> dict[str, dict[str, float | int]]:
    return {symbol: {"trailing_start_bp": start_bp, "trailing_drawback_pct": drawback_pct} for symbol in symbols}


CANDIDATES: dict[str, dict[str, dict[str, float | int]]] = {
    "base": {},
    "ap_tight_150_015": _trailing(["AP888"], 150, 0.15),
    "a_tight_150_015": _trailing(["A888"], 150, 0.15),
    "zn_tight_150_015": _trailing(["ZN888"], 150, 0.15),
    "ap_a_zn_tight_150_015": _trailing(["AP888", "A888", "ZN888"], 150, 0.15),
    "ap_a_zn_mid_200_020": _trailing(["AP888", "A888", "ZN888"], 200, 0.20),
    "ap_a_zn_soft_250_020": _trailing(["AP888", "A888", "ZN888"], 250, 0.20),
    "ap_a_tight_150_015": _trailing(["AP888", "A888"], 150, 0.15),
    "ap_zn_tight_150_015": _trailing(["AP888", "ZN888"], 150, 0.15),
    "a_zn_tight_150_015": _trailing(["A888", "ZN888"], 150, 0.15),
}

DEFAULT_SYMBOL_SET_NAMES = ["all5", "no_RB", "no_SC", "core_AP_A_ZN", "no_A", "no_ZN"]


def _patch_evaluator(overrides: dict[str, Any], multiplier: float):
    import portfolio_goal_evaluator as evaluator

    original = evaluator._scenario_params
    original_run_symbol = evaluator._run_symbol
    scenario = "candidate"
    cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def scenario_params(name: str, symbol: str) -> dict[str, Any]:
        if name != scenario:
            return original(name, symbol)
        params = params_for_multiplier(multiplier, symbol)
        params["block_1buy_daily_down"] = True
        trailing = copy.deepcopy(params.get("trailing_overrides") or {})
        trailing.update(copy.deepcopy(overrides))
        params["trailing_overrides"] = trailing
        return params

    def run_symbol_cached(db_path: Path, symbol: str, start: str, end: str, name: str) -> dict[str, Any]:
        key = (symbol, start, end, name)
        if key not in cache:
            cache[key] = original_run_symbol(db_path, symbol, start, end, name)
        return copy.deepcopy(cache[key])

    evaluator._scenario_params = scenario_params
    evaluator._run_symbol = run_symbol_cached
    return evaluator, original, original_run_symbol, scenario


def _selected_windows(db_path: Path, symbols: list[str], scenario: str, window_names: list[str]) -> dict[str, Any]:
    rows = {}
    positive = 0
    for name in window_names:
        start, end = WINDOWS[name]
        item = _evaluate_period(db_path, symbols, start, end, scenario)
        rows[name] = item["metrics"]
        if item["metrics"]["return_pct"] > 0:
            positive += 1
    total = len(window_names)
    return {
        "positive_windows": positive,
        "total_windows": total,
        "positive_ratio": positive / total if total else 0,
        "windows": rows,
    }


def _evaluate_candidate(
    db_path: Path,
    name: str,
    overrides: dict[str, Any],
    multiplier: float,
    symbol_set_names: list[str],
    window_names: list[str] | None,
) -> dict[str, Any]:
    evaluator, original, original_run_symbol, scenario = _patch_evaluator(overrides, multiplier)
    try:
        all5_oos = _evaluate_period(db_path, SYMBOL_SETS["all5"], OOS_START, OOS_END, scenario)
        all5_wf = _walk_forward(db_path, SYMBOL_SETS["all5"], scenario) if window_names is None else _selected_windows(
            db_path, SYMBOL_SETS["all5"], scenario, window_names
        )
        symbol_sets = {}
        for set_name in symbol_set_names:
            symbols = SYMBOL_SETS[set_name]
            oos = _evaluate_period(db_path, symbols, OOS_START, OOS_END, scenario)
            wf = _walk_forward(db_path, symbols, scenario) if window_names is None else _selected_windows(
                db_path, symbols, scenario, window_names
            )
            symbol_sets[set_name] = {
                "symbols": symbols,
                "out_sample": oos,
                "walk_forward": wf,
                "goal_status": _scaled_goal_status(oos, wf, len(symbols)),
            }
        pass_count = sum(1 for row in symbol_sets.values() if row["goal_status"]["passed"])
        return {
            "candidate": name,
            "overrides": copy.deepcopy(overrides),
            "base": {"block_1buy_daily_down": True, "multiplier": multiplier},
            "all5": {
                "out_sample": all5_oos,
                "walk_forward": all5_wf,
                "goal_status": _goal_status(all5_oos, all5_wf),
            },
            "symbol_sets": symbol_sets,
            "symbol_set_pass_count": pass_count,
            "symbol_set_total": len(symbol_sets),
            "symbol_set_pass_ratio": pass_count / len(symbol_sets) if symbol_sets else 0.0,
        }
    finally:
        evaluator._scenario_params = original
        evaluator._run_symbol = original_run_symbol


def build_report(
    db_path: Path,
    multiplier: float,
    candidates: list[str],
    symbol_set_names: list[str],
    window_names: list[str] | None,
) -> dict[str, Any]:
    rows = {
        name: _evaluate_candidate(db_path, name, CANDIDATES[name], multiplier, symbol_set_names, window_names)
        for name in candidates
    }
    return {"multiplier": multiplier, "symbol_sets": symbol_set_names, "windows": window_names or "all", "rows": rows}


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Platform Trailing Candidates",
        "",
        f"- base: `block_1buy_daily_down + SC short multiplier {payload['multiplier']}`",
        "- Goal: protect weak adjacent symbol sets without shortening every profitable long hold.",
        "",
        "| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in payload["rows"].items():
        metrics = row["all5"]["out_sample"]["metrics"]
        wf = row["all5"]["walk_forward"]
        failing_sets = [s for s, item in row["symbol_sets"].items() if not item["goal_status"]["passed"]]
        lines.append(
            f"| {name} | {row['all5']['goal_status']['passed']} | "
            f"{row['symbol_set_pass_count']}/{row['symbol_set_total']} | "
            f"{_fmt_num(metrics['trades'], 0)} | {_fmt_num(metrics['profit_factor'])} | "
            f"{_fmt_pct(metrics['max_drawdown_pct'])} | {_fmt_num(metrics['sharpe'])} | "
            f"{_fmt_num(metrics['calmar'])} | {wf['positive_windows']}/{wf['total_windows']} | "
            f"{', '.join(failing_sets) or '-'} |"
        )
    lines.extend(["", "## Symbol-Set Detail", ""])
    for name, row in payload["rows"].items():
        lines.extend([
            f"### {name}",
            "",
            f"- overrides: `{json.dumps(row['overrides'], ensure_ascii=False)}`",
            "",
            "| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ])
        for set_name, item in row["symbol_sets"].items():
            metrics = item["out_sample"]["metrics"]
            bh = item["out_sample"]["buy_hold"]
            wf = item["walk_forward"]
            status = item["goal_status"]
            fails = [key for key, ok in status["checks"].items() if not ok]
            lines.append(
                f"| {set_name} | {status['passed']} | "
                f"{_fmt_num(metrics['trades'], 0)}/{_fmt_num(status['min_trades'], 0)} | "
                f"{_fmt_num(metrics['profit_factor'])} | {_fmt_pct(metrics['max_drawdown_pct'])} | "
                f"{_fmt_num(metrics['sharpe'])} | {_fmt_num(metrics['calmar'])} | "
                f"{wf['positive_windows']}/{wf['total_windows']} | "
                f"{_fmt_num(bh['sharpe'])} | {_fmt_num(bh['calmar'])} | "
                f"{', '.join(fails) or '-'} |"
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan trailing-stop candidates from the current platform base.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--multiplier", type=float, default=0.75)
    parser.add_argument("--candidates", nargs="+", default=["base", "ap_a_zn_mid_200_020"])
    parser.add_argument("--sets", nargs="+", default=DEFAULT_SYMBOL_SET_NAMES, choices=sorted(SYMBOL_SETS))
    parser.add_argument("--windows", nargs="*", default=None, choices=sorted(WINDOWS))
    parser.add_argument("--out-json", type=Path, default=HERE / "platform_trailing_candidates.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "platform_trailing_candidates.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, args.multiplier, args.candidates, args.sets, args.windows)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

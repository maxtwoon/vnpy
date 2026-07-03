from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent

from portfolio_goal_evaluator import (  # noqa: E402
    GOAL,
    _fmt_num,
    _fmt_pct,
    _json_safe,
    _walk_forward,
    _evaluate_period,
    OOS_START,
    OOS_END,
)
from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402


SYMBOL_SETS = {
    "all5": ["AP888", "RB888", "SC888", "A888", "ZN888"],
    "no_AP": ["RB888", "SC888", "A888", "ZN888"],
    "no_RB": ["AP888", "SC888", "A888", "ZN888"],
    "no_SC": ["AP888", "RB888", "A888", "ZN888"],
    "no_A": ["AP888", "RB888", "SC888", "ZN888"],
    "no_ZN": ["AP888", "RB888", "SC888", "A888"],
    "core_AP_A_ZN": ["AP888", "A888", "ZN888"],
    "metals_energy": ["RB888", "SC888", "ZN888"],
}


def _scaled_goal_status(oos: dict[str, Any], wf: dict[str, Any], symbol_count: int) -> dict[str, Any]:
    metrics = oos["metrics"]
    scale = symbol_count / 5
    min_trades = max(1, int(round(GOAL["min_trades"] * scale)))
    checks = {
        "trades_ge_scaled_min": metrics["trades"] >= min_trades,
        "pf_ge_1_2": metrics["profit_factor"] >= GOAL["min_profit_factor"],
        "drawdown_le_20": metrics["max_drawdown_pct"] <= GOAL["max_drawdown_pct"],
        "sharpe_ge_0_5": metrics["sharpe"] >= GOAL["min_sharpe"],
        "calmar_ge_0_5": metrics["calmar"] >= GOAL["min_calmar"],
        "walk_forward_ge_2_3": wf["positive_ratio"] >= GOAL["min_positive_walk_forward_ratio"],
        "risk_adjusted_gt_buy_hold": bool(metrics["risk_adjusted_better_than_buy_hold"]),
    }
    return {"checks": checks, "passed": all(checks.values()), "min_trades": min_trades}


def build_report(db_path: Path, scenario: str, set_names: list[str]) -> dict[str, Any]:
    rows = {}
    for name in set_names:
        symbols = SYMBOL_SETS[name]
        oos = _evaluate_period(db_path, symbols, OOS_START, OOS_END, scenario)
        wf = _walk_forward(db_path, symbols, scenario)
        status = _scaled_goal_status(oos, wf, len(symbols))
        rows[name] = {
            "symbols": symbols,
            "out_sample": oos,
            "walk_forward": wf,
            "goal_status": status,
        }
    pass_count = sum(1 for row in rows.values() if row["goal_status"]["passed"])
    total = len(rows)
    return {
        "scenario": scenario,
        "set_names": set_names,
        "pass_count": pass_count,
        "total": total,
        "pass_ratio": pass_count / total if total else 0.0,
        "rows": rows,
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Symbol-Set Stability Scan",
        "",
        f"- scenario: `{payload['scenario']}`",
        f"- pass ratio: `{payload['pass_count']}/{payload['total']}` = `{payload['pass_ratio'] * 100:.2f}%`",
        "",
        "| set | symbols | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in payload["rows"].items():
        m = row["out_sample"]["metrics"]
        bh = row["out_sample"]["buy_hold"]
        wf = row["walk_forward"]
        status = row["goal_status"]
        failing = [name for name, passed in status["checks"].items() if not passed]
        lines.append(
            f"| {name} | {', '.join(row['symbols'])} | {row['goal_status']['passed']} | "
            f"{_fmt_num(m['trades'], 0)}/{_fmt_num(status['min_trades'], 0)} | {_fmt_num(m['profit_factor'])} | "
            f"{_fmt_pct(m['max_drawdown_pct'])} | {_fmt_num(m['sharpe'])} | "
            f"{_fmt_num(m['calmar'])} | {wf['positive_windows']}/{wf['total_windows']} | "
            f"{_fmt_num(bh['sharpe'])} | {_fmt_num(bh['calmar'])} | {', '.join(failing) or '-'} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "A candidate should not be promoted to a stable platform unless neighboring symbol sets also pass. "
        "If only one exact set passes, the edge is symbol-selection fragile.",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate whether a candidate survives adjacent symbol-set changes.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--scenario", default="expanded_short_sc_0847")
    parser.add_argument(
        "--sets",
        nargs="+",
        default=["all5", "no_RB", "no_SC", "core_AP_A_ZN"],
        choices=sorted(SYMBOL_SETS),
    )
    parser.add_argument("--out-json", type=Path, default=HERE / "symbol_set_stability_scan.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "symbol_set_stability_scan.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, args.scenario, args.sets)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"pass_ratio={payload['pass_count']}/{payload['total']}")


if __name__ == "__main__":
    main()

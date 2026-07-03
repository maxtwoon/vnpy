from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _combo(payload: dict[str, Any], period: str, scenario: str) -> dict[str, Any]:
    return payload["periods"][period]["scenarios"][scenario]["combo"]


def _delta(payload: dict[str, Any], period: str, scenario: str) -> dict[str, float]:
    base = _combo(payload, period, "baseline")
    item = _combo(payload, period, scenario)
    return {
        "return_delta": float(item["return_pct"]) - float(base["return_pct"]),
        "drawdown_delta": float(item["max_drawdown_pct"]) - float(base["max_drawdown_pct"]),
        "trade_delta": float(item["total_trades"]) - float(base["total_trades"]),
    }


def _decision(payload: dict[str, Any], scenario: str) -> str:
    oos = _delta(payload, "out_sample", scenario)
    full = _delta(payload, "full", scenario)
    base_oos_trades = float(_combo(payload, "out_sample", "baseline")["total_trades"])
    trade_drop = -oos["trade_delta"] / base_oos_trades if base_oos_trades else 0.0
    if (
        oos["return_delta"] > 0
        and oos["drawdown_delta"] <= 0
        and full["return_delta"] >= 0
        and trade_drop <= 0.30
    ):
        return "candidate"
    if oos["return_delta"] > 0 and full["return_delta"] >= 0 and trade_drop <= 0.30:
        return "watchlist"
    if oos["return_delta"] > 0:
        return "oos_only"
    return "reject"


def write_report(payload: dict[str, Any], out: Path) -> None:
    scenarios = [s for s in payload["scenarios"] if s != "baseline"]
    lines = [
        "# Strategy Experiment Decision Report",
        "",
        f"- source: `{out.with_name('strategy_execution_experiment_matrix.json')}`",
        "- rule: out_sample is primary; full sample is a stability check.",
        "- candidate gate: OOS return improves, OOS drawdown does not worsen, full-sample return does not worsen, and OOS trade loss is <= 30%.",
        "",
        "## Combo Summary",
        "",
        "| period | scenario | return | drawdown | trades | return_delta | drawdown_delta | decision |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for period in ["full", "out_sample"]:
        for scenario in ["baseline", *scenarios]:
            combo = _combo(payload, period, scenario)
            if scenario == "baseline":
                ret_delta = 0.0
                dd_delta = 0.0
                decision = "-"
            else:
                d = _delta(payload, period, scenario)
                ret_delta = d["return_delta"]
                dd_delta = d["drawdown_delta"]
                decision = _decision(payload, scenario) if period == "out_sample" else "-"
            lines.append(
                f"| {period} | {scenario} | {_fmt_pct(combo['return_pct'])} | "
                f"{_fmt_pct(combo['max_drawdown_pct'])} | {_fmt_num(combo['total_trades'], 0)} | "
                f"{_fmt_pct(ret_delta)} | {_fmt_pct(dd_delta)} | {decision} |"
            )

    lines.extend(["", "## Recommendation", ""])
    decisions = {scenario: _decision(payload, scenario) for scenario in scenarios}
    combined = decisions.get("combined")
    second_buy = decisions.get("second_buy_filters")
    trailing = decisions.get("trailing_overrides")

    if combined in {"candidate", "watchlist"}:
        lines.append("- combined: can enter next paper-trading candidate set; keep default-off until SimNow confirms execution quality.")
    else:
        lines.append("- combined: do not promote as default; keep as diagnostics-only.")

    if second_buy in {"candidate", "watchlist", "oos_only"}:
        lines.append("- second_buy_filters: keep testing as a targeted risk gate for chase entries; monitor trade count loss.")
    else:
        lines.append("- second_buy_filters: current matrix does not support promotion.")

    if trailing in {"candidate", "watchlist", "oos_only"}:
        lines.append("- trailing_overrides: RB888/SC888 overrides remain worth paper-trading because they are per-symbol and explicit.")
    else:
        lines.append("- trailing_overrides: keep default trailing params for now.")

    lines.extend([
        "",
        "## Parameters Under Test",
        "",
        "```json",
        json.dumps(payload["scenarios"], ensure_ascii=False, indent=2),
        "```",
        "",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a decision report from strategy_execution_experiment_matrix.json.")
    parser.add_argument(
        "--matrix-json",
        type=Path,
        default=Path(__file__).with_name("strategy_execution_experiment_matrix.json"),
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path(__file__).with_name("strategy_experiment_decision_report.md"),
    )
    args = parser.parse_args()

    payload = json.loads(args.matrix_json.read_text(encoding="utf-8"))
    write_report(payload, args.out_md)
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

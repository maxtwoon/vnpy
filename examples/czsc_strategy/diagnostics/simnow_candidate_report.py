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


def _rolling_summary(rolling: dict[str, Any], scenario: str) -> dict[str, Any]:
    rows = []
    for window_name, window in rolling["windows"].items():
        base = window["scenarios"]["baseline"]["combo"]
        item = window["scenarios"][scenario]["combo"]
        rows.append({
            "window": window_name,
            "return_delta": float(item["return_pct"]) - float(base["return_pct"]),
            "drawdown_delta": float(item["max_drawdown_pct"]) - float(base["max_drawdown_pct"]),
            "trade_delta": int(item["total_trades"]) - int(base["total_trades"]),
        })
    return {
        "positive_return_windows": sum(1 for r in rows if r["return_delta"] > 0),
        "non_worse_drawdown_windows": sum(1 for r in rows if r["drawdown_delta"] <= 0),
        "total_windows": len(rows),
        "rows": rows,
    }


def write_report(
    execution: dict[str, Any],
    rolling: dict[str, Any],
    extreme: dict[str, Any],
    review: dict[str, Any],
    out: Path,
) -> None:
    oos_combo = execution["periods"]["out_sample"]["scenarios"]["combined"]["combo"]
    oos_base = execution["periods"]["out_sample"]["scenarios"]["baseline"]["combo"]
    rolling_combined = _rolling_summary(rolling, "combined")
    rolling_expanded = _rolling_summary(rolling, "expanded")
    extreme_oos = extreme["periods"]["out_sample"]
    review_oos = review["periods"]["out_sample"]

    lines = [
        "# SimNow Candidate Report",
        "",
        "## Recommended Candidate",
        "",
        "- candidate: `expanded` for paper/SimNow observation, not default live trading.",
        "- base: current `combined` candidate.",
        "- expansion: AP888/A888 are exempt from the 3% second-buy chase filter; RB888/SC888 keep tight trailing `150/0.15` and second-buy disabled by symbol gate.",
        "",
        "## OOS Baseline vs Combined",
        "",
        "| scenario | return | drawdown | trades | win_rate |",
        "|---|---:|---:|---:|---:|",
        f"| baseline | {_fmt_pct(oos_base['return_pct'])} | {_fmt_pct(oos_base['max_drawdown_pct'])} | {_fmt_num(oos_base['total_trades'], 0)} | {_fmt_pct(oos_base['win_rate'] * 100)} |",
        f"| combined | {_fmt_pct(oos_combo['return_pct'])} | {_fmt_pct(oos_combo['max_drawdown_pct'])} | {_fmt_num(oos_combo['total_trades'], 0)} | {_fmt_pct(oos_combo['win_rate'] * 100)} |",
        "",
        "## Rolling Stability",
        "",
        "| scenario | positive_return_windows | non_worse_drawdown_windows | total_windows |",
        "|---|---:|---:|---:|",
        f"| combined | {rolling_combined['positive_return_windows']} | {rolling_combined['non_worse_drawdown_windows']} | {rolling_combined['total_windows']} |",
        f"| expanded | {rolling_expanded['positive_return_windows']} | {rolling_expanded['non_worse_drawdown_windows']} | {rolling_expanded['total_windows']} |",
        "",
        "| window | scenario | return_delta | drawdown_delta | trade_delta |",
        "|---|---|---:|---:|---:|",
    ]
    for scenario, summary in [("combined", rolling_combined), ("expanded", rolling_expanded)]:
        for row in summary["rows"]:
            lines.append(
                f"| {row['window']} | {scenario} | {_fmt_pct(row['return_delta'])} | "
                f"{_fmt_pct(row['drawdown_delta'])} | {_fmt_num(row['trade_delta'], 0)} |"
            )

    lines.extend([
        "",
        "## Extreme Contribution",
        "",
        "| metric | OOS value |",
        "|---|---:|",
        f"| total_impact | {_fmt_pct(extreme_oos['total_impact_pct'])} |",
        f"| without_top1_positive | {_fmt_pct(extreme_oos['without_top1_positive_pct'])} |",
        f"| without_top3_positive | {_fmt_pct(extreme_oos['without_top3_positive_pct'])} |",
        f"| top1_positive_share | {_fmt_pct(extreme_oos['top1_positive_share'] * 100)} |",
        f"| top3_positive_share | {_fmt_pct(extreme_oos['top3_positive_share'] * 100)} |",
        "",
        "## Key Behavior Queue",
        "",
        "| type | symbol | strategy | open_dt | reason | impact | review_hint |",
        "|---|---|---|---|---|---:|---|",
    ])
    for row in review_oos[:10]:
        trade = row["trade"]
        lines.append(
            f"| {row['type']} | {trade.get('requested_symbol')} | {trade.get('strategy')} | "
            f"{trade.get('open_dt')} | {trade.get('reason_code')} | {_fmt_pct(row['impact_pct'])} | {row['review_hint']} |"
        )

    lines.extend([
        "",
        "## SimNow Observation Metrics",
        "",
        "- Track per-symbol return, drawdown, trade count, win rate and stop-loss weighted loss weekly.",
        "- Track RB888/SC888 trailing-stop exits separately; confirm tight trailing reduces drawdown without cutting all large winners.",
        "- Track second-buy stop-loss count. The candidate only makes sense if bad second-buy stop-losses remain suppressed.",
        "- Compare live trade frequency against the rolling-window historical range; abnormal silence is also a failure mode.",
        "",
        "## Kill Switches",
        "",
        "- Any single symbol drawdown exceeds 1.5x its OOS backtest drawdown.",
        "- Portfolio max losing streak exceeds 10, the baseline OOS value.",
        "- Stop-loss weighted loss returns near baseline OOS level (`-21.69%`) on a rolling basis.",
        "- RB888/SC888 generate new stop-loss clusters after the tight trailing override.",
        "- Trade count deviates by more than 50% from the comparable rolling-window historical frequency without an obvious market-regime reason.",
        "",
        "## Decision",
        "",
        "Use `expanded` only as a SimNow candidate. Keep default production config unchanged until live-paper behavior confirms that the improvement is not concentrated in one or two historical trades.",
        "",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final SimNow candidate report.")
    parser.add_argument("--execution-json", type=Path, default=Path(__file__).with_name("strategy_execution_experiment_matrix.json"))
    parser.add_argument("--rolling-json", type=Path, default=Path(__file__).with_name("rolling_candidate_matrix.json"))
    parser.add_argument("--extreme-json", type=Path, default=Path(__file__).with_name("extreme_trade_contribution_audit.json"))
    parser.add_argument("--review-json", type=Path, default=Path(__file__).with_name("key_trade_behavior_review.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("simnow_candidate_report.md"))
    args = parser.parse_args()

    write_report(
        json.loads(args.execution_json.read_text(encoding="utf-8")),
        json.loads(args.rolling_json.read_text(encoding="utf-8")),
        json.loads(args.extreme_json.read_text(encoding="utf-8")),
        json.loads(args.review_json.read_text(encoding="utf-8")),
        args.out_md,
    )
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

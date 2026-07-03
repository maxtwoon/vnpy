from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _collect_rows(diff: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for trade in diff["removed"]:
        impact = -float(trade.get("weighted_pnl_pct", 0))
        rows.append({"type": "removed", "impact_pct": impact, "trade": trade})
    for trade in diff["added"]:
        impact = float(trade.get("weighted_pnl_pct", 0))
        rows.append({"type": "added", "impact_pct": impact, "trade": trade})
    for item in diff["changed"]:
        trade = item["combined"]
        base = item["baseline"]
        rows.append({
            "type": "changed",
            "impact_pct": float(item.get("weighted_delta_pct", 0)),
            "trade": trade,
            "baseline_trade": base,
        })
    return sorted(rows, key=lambda x: abs(float(x["impact_pct"])), reverse=True)


def _review_hint(row: dict[str, Any]) -> str:
    trade = row["trade"]
    typ = row["type"]
    reason = trade.get("reason_code")
    impact = float(row["impact_pct"])
    if typ == "removed" and reason == "stop_loss" and impact > 0:
        return "strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure."
    if typ == "removed" and impact < 0:
        return "negative: profitable trade was filtered out; check whether the filter is too strict."
    if typ == "changed" and reason == "trailing_stop" and impact > 0:
        return "strong: tighter trailing locked profit or reduced give-back."
    if typ == "changed" and reason == "trailing_stop" and impact < 0:
        return "negative: tighter trailing exited too early and lost follow-through profit."
    if typ == "added" and reason == "stop_loss":
        return "risk: parameter change introduced a new stop-loss trade."
    if typ == "added" and impact > 0:
        return "positive add: check whether shorter trailing released the entry interval."
    return "manual replay required."


def build_report(attribution: dict[str, Any], limit: int) -> dict[str, Any]:
    payload: dict[str, Any] = {"periods": {}}
    for period_name, period in attribution["periods"].items():
        rows = _collect_rows(period["symbols"]["_portfolio"]["diff"])[:limit]
        payload["periods"][period_name] = [
            {
                "type": row["type"],
                "impact_pct": row["impact_pct"],
                "trade": row["trade"],
                "baseline_trade": row.get("baseline_trade"),
                "review_hint": _review_hint(row),
            }
            for row in rows
        ]
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Key Trade Behavior Review",
        "",
        "- This is a structured review queue, not a replacement for chart replay.",
        "- Positive impact means combined is better than baseline for that trade event.",
        "",
    ]
    for period_name, rows in payload["periods"].items():
        lines.extend([
            f"## {period_name}",
            "",
            "| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl | review_hint |",
            "|---|---|---|---|---|---|---:|---:|---|",
        ])
        for row in rows:
            trade = row["trade"]
            lines.append(
                f"| {row['type']} | {trade.get('requested_symbol')} | {trade.get('strategy')} | "
                f"{trade.get('open_dt')} | {trade.get('close_dt')} | {trade.get('reason_code')} | "
                f"{_fmt_pct(row['impact_pct'])} | {_fmt_pct(float(trade.get('pnl_pct', 0)) * 100)} | {row['review_hint']} |"
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a review queue for the largest changed trades.")
    parser.add_argument("--attribution-json", type=Path, default=Path(__file__).with_name("trade_difference_attribution.json"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("key_trade_behavior_review.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("key_trade_behavior_review.md"))
    args = parser.parse_args()

    attribution = json.loads(args.attribution_json.read_text(encoding="utf-8"))
    payload = build_report(attribution, args.limit)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()

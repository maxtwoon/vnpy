from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _impact_rows(diff: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for trade in diff["removed"]:
        rows.append({
            "type": "removed",
            "symbol": trade.get("requested_symbol"),
            "strategy": trade.get("strategy"),
            "open_dt": trade.get("open_dt"),
            "close_dt": trade.get("close_dt"),
            "reason_code": trade.get("reason_code"),
            "impact_pct": -float(trade.get("weighted_pnl_pct", 0)),
            "pnl_pct": float(trade.get("pnl_pct", 0)) * 100,
        })
    for trade in diff["added"]:
        rows.append({
            "type": "added",
            "symbol": trade.get("requested_symbol"),
            "strategy": trade.get("strategy"),
            "open_dt": trade.get("open_dt"),
            "close_dt": trade.get("close_dt"),
            "reason_code": trade.get("reason_code"),
            "impact_pct": float(trade.get("weighted_pnl_pct", 0)),
            "pnl_pct": float(trade.get("pnl_pct", 0)) * 100,
        })
    for item in diff["changed"]:
        trade = item["combined"]
        rows.append({
            "type": "changed",
            "symbol": trade.get("requested_symbol"),
            "strategy": trade.get("strategy"),
            "open_dt": trade.get("open_dt"),
            "close_dt": trade.get("close_dt"),
            "reason_code": trade.get("reason_code"),
            "impact_pct": float(item.get("weighted_delta_pct", 0)),
            "pnl_pct": float(trade.get("pnl_pct", 0)) * 100,
        })
    return rows


def _robustness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(float(x["impact_pct"]) for x in rows)
    positives = sorted([r for r in rows if r["impact_pct"] > 0], key=lambda x: x["impact_pct"], reverse=True)
    negatives = sorted([r for r in rows if r["impact_pct"] < 0], key=lambda x: x["impact_pct"])
    return {
        "total_impact_pct": total,
        "without_top1_positive_pct": total - sum(x["impact_pct"] for x in positives[:1]),
        "without_top3_positive_pct": total - sum(x["impact_pct"] for x in positives[:3]),
        "without_bottom1_negative_pct": total - sum(x["impact_pct"] for x in negatives[:1]),
        "without_bottom3_negative_pct": total - sum(x["impact_pct"] for x in negatives[:3]),
        "top1_positive_share": positives[0]["impact_pct"] / total if total and positives else 0,
        "top3_positive_share": sum(x["impact_pct"] for x in positives[:3]) / total if total and positives else 0,
        "top_positive": positives[:10],
        "top_negative": negatives[:10],
    }


def build_report(attribution: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"periods": {}}
    for period_name, period in attribution["periods"].items():
        rows = _impact_rows(period["symbols"]["_portfolio"]["diff"])
        payload["periods"][period_name] = _robustness(rows)
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Extreme Trade Contribution Audit",
        "",
        "- Uses `trade_difference_attribution.json` and audits whether the improvement depends on a few extreme trades.",
        "",
        "| period | total_impact | without_top1_positive | without_top3_positive | without_bottom1_negative | without_bottom3_negative | top1_positive_share | top3_positive_share |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for period_name, row in payload["periods"].items():
        lines.append(
            f"| {period_name} | {_fmt_pct(row['total_impact_pct'])} | {_fmt_pct(row['without_top1_positive_pct'])} | "
            f"{_fmt_pct(row['without_top3_positive_pct'])} | {_fmt_pct(row['without_bottom1_negative_pct'])} | "
            f"{_fmt_pct(row['without_bottom3_negative_pct'])} | {_fmt_pct(row['top1_positive_share'] * 100)} | "
            f"{_fmt_pct(row['top3_positive_share'] * 100)} |"
        )
    for period_name, row in payload["periods"].items():
        lines.extend(["", f"## {period_name} Top Positive", "", "| type | symbol | strategy | open_dt | reason | impact | pnl |", "|---|---|---|---|---|---:|---:|"])
        for item in row["top_positive"]:
            lines.append(
                f"| {item['type']} | {item['symbol']} | {item['strategy']} | {item['open_dt']} | "
                f"{item['reason_code']} | {_fmt_pct(item['impact_pct'])} | {_fmt_pct(item['pnl_pct'])} |"
            )
        lines.extend(["", f"## {period_name} Top Negative", "", "| type | symbol | strategy | open_dt | reason | impact | pnl |", "|---|---|---|---|---|---:|---:|"])
        for item in row["top_negative"]:
            lines.append(
                f"| {item['type']} | {item['symbol']} | {item['strategy']} | {item['open_dt']} | "
                f"{item['reason_code']} | {_fmt_pct(item['impact_pct'])} | {_fmt_pct(item['pnl_pct'])} |"
            )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit extreme contribution in trade-difference attribution.")
    parser.add_argument("--attribution-json", type=Path, default=Path(__file__).with_name("trade_difference_attribution.json"))
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("extreme_trade_contribution_audit.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("extreme_trade_contribution_audit.md"))
    args = parser.parse_args()

    attribution = json.loads(args.attribution_json.read_text(encoding="utf-8"))
    payload = build_report(attribution)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
